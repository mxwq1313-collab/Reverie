"""Whitespace aliases never create a second person or change archived source records."""
from pathlib import Path
import copy,hashlib,json,sqlite3,tempfile,unittest
from PIL import Image
from wechat_archive.identity import canonical_identity,alias_only_source_change
from wechat_archive.importer.rich_importer import FORMAT,create_rich_archive,RichImporter,ready_media
from wechat_archive.ui.application_controller import ApplicationController,ReadOnlyArchive
from wechat_archive.wechat_source.rich_source import source_sender,normalize_row,source_stats
from test_rich_source import FakeSource

class IdentityAliasTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.folder=Path(self.temp.name)
        self.db=self.folder/'archive.db';create_rich_archive(self.db);self.source=self.folder/'exchange.json'
        Image.new('RGB',(24,18),'blue').save(self.folder/'photo.png')
        frames=[Image.new('RGB',(20,16),c) for c in ('red','green')];frames[0].save(self.folder/'sticker.gif',save_all=True,append_images=frames[1:],duration=80,loop=0)
        self.payload={'format':FORMAT,'format_version':'2.0','namespace':'wechat:unit_account',
            'users':[{'id':'unit_me','nickname':'自己'},{'id':'unit_peer','nickname':'同学'},{'id':'unit_peer ','nickname':'unit_peer '}],
            'chats':[{'id':'unit_group@chatroom','kind':'group','title':'自建小组','members':['unit_me','unit_peer','unit_peer ']},
                     {'id':'private_clean','kind':'private','members':['unit_me','unit_peer']},
                     {'id':'private_padded','kind':'private','members':['unit_me','unit_peer ']}],
            'messages':[{'id':'photo','chat_id':'unit_group@chatroom','sender_id':'unit_peer ','receiver_id':None,'create_time':'2026-01-01T00:00:00+00:00','kind':'image','content':'[图片]','attachments':[{'kind':'image','path':'photo.png'}]},
                        {'id':'sticker','chat_id':'unit_group@chatroom','sender_id':'unit_peer ','receiver_id':None,'create_time':'2026-01-01T00:00:01+00:00','kind':'emoji','content':'[表情]','attachments':[{'kind':'image','path':'sticker.gif'}]},
                        {'id':'private_photo','chat_id':'private_padded','sender_id':'unit_peer ','receiver_id':'unit_me','create_time':'2026-01-01T00:00:02+00:00','kind':'image','content':'[图片]','attachments':[{'kind':'image','path':'photo.png'}]}]}
        self.write();report=RichImporter(self.db).import_file(self.source);self.assertEqual(report.success_count,3)
        self.controller=ApplicationController(self.folder/'profile');self.controller.open_archive(self.db)
    def write(self):self.source.write_text(json.dumps(self.payload,ensure_ascii=False),encoding='utf-8')
    def raw(self):
        with sqlite3.connect(self.db) as conn:return list(conn.execute('SELECT * FROM messages ORDER BY id'))
    def test_canonicalization_is_limited_to_registered_namespace_and_same_account(self):
        self.assertEqual(canonical_identity('wechat:unit_account:unit_peer%20'),'wechat:unit_account:unit_peer')
        self.assertNotEqual(canonical_identity('wechat:other_account:unit_peer%20'),'wechat:unit_account:unit_peer')
        self.assertEqual(canonical_identity('custom:unit_peer%20'),'custom:unit_peer%20')
        self.assertEqual(canonical_identity('wechat:unit_account:unit%20peer'),'wechat:unit_account:unit%20peer')
    def test_photo_and_gif_sender_resolve_without_archive_or_media_edits(self):
        before=hashlib.sha256(self.db.read_bytes()).hexdigest();rows=self.controller.messages(1,-1)['items'];self.assertEqual(len(rows),2)
        for row in rows:
            self.assertEqual(row['sender_id'],2);self.assertEqual(row['sender_name'],'同学');self.assertEqual(row['sender_wxid'],'wechat:unit_account:unit_peer')
            file=ready_media(self.db,row['attachments'][0])
            with Image.open(file) as im:
                if row['external_id']=='sticker':self.assertEqual(im.n_frames,2)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(),before)
        with sqlite3.connect(self.db) as conn:self.assertEqual(conn.execute('SELECT sender_id FROM messages WHERE id=1').fetchone()[0],3)
    def test_ai_readonly_connection_uses_the_same_canonical_identity(self):
        from wechat_archive.agent.tools import ReadOnlyArchive as ToolArchive
        with ToolArchive(self.db).connection() as conn:
            row=conn.execute('SELECT m.sender_id,u.nickname FROM messages m JOIN users u ON u.id=m.sender_id WHERE m.id=1').fetchone()
            self.assertEqual(tuple(row),(2,'同学'));self.assertTrue(conn.execute('PRAGMA query_only').fetchone()[0])

    def test_private_scope_and_context_use_same_identity(self):
        result=self.controller.messages(1,2);self.assertEqual(result['total'],1);self.assertEqual(result['items'][0]['sender_name'],'同学')
        context=self.controller.message_context(1,3);self.assertEqual(context['peer_id'],2);self.assertEqual(context['target_id'],3)
        self.assertIn(3,[r['id'] for r in context['items']])
    def test_group_members_and_saved_view_do_not_duplicate_aliases(self):
        self.assertEqual([r['id'] for r in self.controller.users()],[1,2])
        self.controller.save_view(3,1);self.assertEqual(self.controller.view_state()['owner_id'],2)
        contact=next(r for r in self.controller.contacts(1) if r['id']==-1)
        self.assertEqual(len(contact['members']),2);self.assertEqual(sum(r['message_count'] for r in contact['members']),2)
    def test_temporary_identity_views_leave_main_readonly_and_transactions_usable(self):
        with ReadOnlyArchive(self.db).connection() as conn:
            self.assertFalse(conn.in_transaction);conn.execute('BEGIN')
            self.assertEqual(conn.execute('SELECT sender_id FROM messages WHERE id=1').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT sender_id FROM main.messages WHERE id=1').fetchone()[0],3)
            with self.assertRaises(sqlite3.OperationalError):conn.execute("UPDATE main.users SET nickname='changed' WHERE id=2")
    def test_normalized_reread_is_deduplicated_but_real_content_change_is_rejected(self):
        before=self.raw()
        for row in self.payload['messages']:row['sender_id']='unit_peer'
        self.payload['users']=[row for row in self.payload['users'] if row['id']!='unit_peer ']
        for chat in self.payload['chats']:chat['members']=list(dict.fromkeys(member.strip() for member in chat['members']))
        self.write();report=RichImporter(self.db).import_file(self.source);self.assertEqual(report.duplicated_count,3);self.assertEqual(self.raw(),before)
        with sqlite3.connect(self.db) as conn:
            original=conn.execute('SELECT source_hash FROM message_sources WHERE message_id=1').fetchone()[0]
            row=copy.deepcopy(self.payload['messages'][0]);row['content']='被改变的原文'
            self.assertFalse(alias_only_source_change(conn,self.payload['namespace'],row,1,original))
    def test_same_name_in_another_source_account_never_gains_group_access(self):
        from wechat_archive.errors import NotFoundError
        with sqlite3.connect(self.db) as conn:
            conn.execute('INSERT INTO users(wxid,nickname) VALUES (?,?)',('wechat:other_account:unit_peer','同学'))
            conn.execute('INSERT INTO users(wxid,nickname) VALUES (?,?)',('wechat:other_account:unit_peer%20','unit_peer '))
        self.assertEqual([r['id'] for r in self.controller.users()],[1,2,4])
        with self.assertRaises(NotFoundError):self.controller.message_context(4,1)
    def test_genuinely_unknown_sender_stays_unmapped(self):
        self.payload['messages'].append({'id':'unknown','chat_id':'unit_group@chatroom','sender_id':None,'receiver_id':None,'create_time':'2026-01-01T00:00:03+00:00','kind':'system','content':'[发送者未映射]\n[表情]','attachments':[]})
        self.write();RichImporter(self.db).import_file(self.source)
        row=next(r for r in self.controller.messages(1,-1)['items'] if r['external_id']=='unknown')
        self.assertIsNone(row['sender_id']);self.assertIn('未映射',row['sender_name'])

    def test_source_projection_cleans_sender_padding_before_mapping(self):
        folder=self.folder/'source';folder.mkdir();source=FakeSource(folder,count=2,shards=1);self.addCleanup(source.close)
        connection,table=source.tables[0];connection.execute("UPDATE Name2Id SET user_name=user_name||' '");connection.commit()
        stats=source_stats(source,source.peer);self.assertEqual(stats['unresolved_count'],0);self.assertEqual(stats['own_count'],1)
        for kind in (3,47):
            row={'local_type':kind,'sender_username':'synthetic_peer ','message_content':'[自建媒体]','shard':'unit','local_id':kind,'server_id':kind,'create_time':1767225600}
            users={source.wxid:{},'synthetic_peer':{}};result=normalize_row(source,source.peer,row,users)
            self.assertEqual(result['sender_id'],'synthetic_peer');self.assertNotIn('unmapped_kind',result)
        self.assertEqual(source_sender(source.peer,{'sender_username':'','message_content':'synthetic_peer :\n<msg/>'},{'synthetic_peer'}),'synthetic_peer')

if __name__=='__main__':unittest.main(verbosity=2)
