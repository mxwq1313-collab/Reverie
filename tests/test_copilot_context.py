"""Context and transport evidence use self-created records and the offline server."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from wechat_archive.agent import ArchiveScope
from wechat_archive.ai import ContextProvider,AIService
from wechat_archive.errors import ConflictError
from wechat_archive.ui.application_controller import ApplicationController


class CopilotContextTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name);self.controller=ApplicationController(self.folder/'profile')
        self.controller.new_archive(self.folder/'unit.db')
        for key,name in (('unit_owner','自己'),('unit_peer','当前联系人'),('unit_other','另一个联系人')):
            self.controller.manage_user('create',wxid=key,nickname=name)
        self.controller.manage_message('create',sender_id=2,receiver_id=1,content='BODY_NOT_AUTOMATICALLY_SENT',create_time='2026-10-14T00:00:00Z')
        self.app=SimpleNamespace(controller=self.controller,owner_id=1,peer_id=2,current_subpage='聊天归档',
            loaded_query=(1,2,'论文','2026-10-01','2026-10-14'))
        self.scope=ArchiveScope(self.controller.database,1,2);self.provider=ContextProvider(self.app);self.service=AIService(self.provider)

    def test_immutable_context_is_bound_and_contains_metadata_not_chat_body_or_path(self):
        before=self.controller.database.read_bytes();context=self.provider.capture(self.scope);payload=context.to_payload()
        self.assertEqual((payload['user_id'],payload['peer_id']),(1,2));self.assertEqual(payload['peer_name'],'当前联系人')
        self.assertEqual(payload['conversation_id'],'private:1:2');self.assertEqual(payload['search_query'],'论文')
        self.assertEqual(payload['date_filter'],{'start':'2026-10-01','end':'2026-10-14'})
        serialized=json.dumps(payload,ensure_ascii=False)
        self.assertNotIn('BODY_NOT_AUTOMATICALLY_SENT',serialized);self.assertNotIn(str(self.folder),serialized)
        self.assertEqual(payload['visible_messages'],[]);self.assertIsNone(payload['current_position'])
        with self.assertRaises(FrozenInstanceError):context.peer_id=3
        self.assertEqual(before,self.controller.database.read_bytes())

    def test_source_change_invalidates_prepared_request(self):
        request=self.service.prepare('这个人说过什么？',self.scope)
        self.controller.manage_message('update',message_id=1,content='new original version')
        client=SimpleNamespace(send=lambda *_args,**_kwargs:self.fail('Stale request must not be sent'))
        with self.assertRaises(ConflictError):self.service.send(client,request)

    def test_contact_change_blocks_request_without_touching_transport(self):
        request=self.service.prepare('这个人说过什么？',self.scope);self.app.peer_id=3
        client=SimpleNamespace(send=lambda *_args,**_kwargs:self.fail('Wrong conversation must not be sent'))
        with self.assertRaises(ConflictError):self.service.send(client,request)

    def test_identity_wide_scope_is_explicit_and_cannot_reuse_private_context(self):
        context=self.provider.capture(self.scope);wide=ArchiveScope(self.scope.path,1)
        with self.assertRaises(ConflictError):context.validate(wide)
        all_context=self.provider.capture(wide)
        self.assertIsNone(all_context.conversation_id);self.assertIsNone(all_context.peer_id)
        self.assertEqual(dict(all_context.metadata)['authorized_range'],'identity_private_chats')

    def test_bounded_search_and_names_do_not_load_messages(self):
        self.controller.manage_user('update',user_id=2,nickname='长名字'*1000)
        self.app.loaded_query=(1,None,'检索'*10000,'2026-10-01','2026-10-14')
        with patch.object(self.controller,'messages',side_effect=AssertionError('No message loading')):
            context=self.provider.capture(self.scope)
        self.assertLessEqual(len(context.peer_name),80);self.assertLessEqual(len(context.search_query),256)
        self.assertLessEqual(len(json.dumps(context.to_payload(),ensure_ascii=False)),4096)

    def test_applied_search_only_and_other_pages_keep_archive_scope(self):
        self.app.current_subpage='导出归档';self.app.loaded_query=(3,1,'other identity','','')
        context=self.provider.capture(self.scope)
        self.assertEqual(context.page,'导出归档');self.assertEqual(context.search_query,'')
        self.assertEqual((context.user_id,context.peer_id),(1,2))

    def test_twelve_thousand_character_question_is_kept_separate(self):
        request=self.service.prepare('问'*12000,self.scope)
        seen=[];client=SimpleNamespace(send=lambda *args,**kwargs:seen.append((args,kwargs)))
        self.service.send(client,request)
        self.assertEqual(len(seen[0][0][0]),12000);self.assertEqual(seen[0][1]['context'].scope_key,request.context.scope_key)

    def test_ui_preparation_never_queries_sqlite_and_worker_resolves_names(self):
        with patch.object(self.provider,'resolve',side_effect=AssertionError('UI must not query SQLite')):
            request=self.service.prepare('当前联系人是谁？',self.scope)
        seen=[];client=SimpleNamespace(send=lambda *args,**kwargs:seen.append(kwargs['context']))
        self.service.send(client,request)
        self.assertEqual(seen[0].peer_name,'当前联系人');self.assertEqual(dict(seen[0].metadata)['display_timezone'],'+08:00')

    def test_scope_change_during_worker_resolution_cannot_send_old_request(self):
        request=self.service.prepare('当前范围问题',self.scope);resolve=self.provider.resolve
        def changed(context,scope):
            result=resolve(context,scope);self.app.peer_id=3;return result
        client=SimpleNamespace(send=lambda *_args,**_kwargs:self.fail('Old scope must not reach transport'))
        with patch.object(self.provider,'resolve',side_effect=changed):
            with self.assertRaises(ConflictError):self.service.send(client,request)
