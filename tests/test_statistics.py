"""Local archive statistics and deferred attachment interactions on generated data."""
import json,time,tkinter as tk
from pathlib import Path
from unittest.mock import patch
from test_sixu_v1 import RichFixture
from wechat_archive.services.archive_statistics import archive_statistics
from wechat_archive.ui.application_window import ApplicationWindow
from wechat_archive.ai.mbti_resources import import_licensed_bank,load_bank,resource_context,SOURCES
from wechat_archive.errors import ValidationError


class StatisticsTests(RichFixture):
    def test_statistics_count_scope_timezone_media_and_preserve_source(self):
        self.payload['messages'].append({'id':'night','chat_id':'private','sender_id':'unit_peer','receiver_id':'unit_self','kind':'text','content':'夜间合成消息','create_time':'2026-10-15T18:30:00Z'})
        self.write();self.importer().import_file(self.source);before=self.db.read_bytes();result=archive_statistics(self.db,1)
        self.assertEqual(result['summary']['total'],5);self.assertEqual(result['summary']['conversations'],2)
        self.assertEqual(result['summary']['groups'],1);self.assertEqual(result['hours'][2],1)
        self.assertEqual(result['summary']['active_days'],2);self.assertEqual(result['fun']['longest_streak'],2)
        self.assertAlmostEqual(result['fun']['night_ratio'],.2);self.assertEqual(result['media']['resources'],2)
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(archive_statistics(self.db,3)['summary']['total'],3)

    def test_empty_archive_has_finite_zero_statistics(self):
        result=archive_statistics(self.db)
        self.assertEqual(result['summary']['total'],0);self.assertEqual(result['hours'],[0]*24)
        self.assertEqual(result['fun']['night_ratio'],0);self.assertIsNone(result['fun']['peak_day'])

    def test_official_resources_have_sources_and_do_not_claim_a_question_bank(self):
        text=resource_context();self.assertIn('当前未导入官方完整题库',text)
        self.assertIn('官方资料资源索引',text)
        self.assertTrue(all(x['url'].startswith('https://') for x in SOURCES))

    def test_licensed_import_requires_permissions_digest_and_bounded_content(self):
        source=self.folder/'licensed-synthetic.json';payload={'format':'sixu-licensed-mbti-bank-v1','source_url':SOURCES[0]['url'],'license':{'publisher':'The Myers-Briggs Company','reference':'SYNTHETIC-UNIT-NOT-REAL-AUTH','allow_model_processing':True},'items':[{'id':'unit','text':'自建授权接口测试占位文字，不是真实测评题。','choices':['自建选项一','自建选项二']}]}
        source.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');key,count=import_licensed_bank(self.folder,source)
        self.assertEqual(count,1);self.assertEqual(load_bank(self.folder,key)['items'],payload['items'])
        self.assertIn('本轮包含 1/1 题',resource_context(self.folder,key))
        payload['license']['allow_model_processing']=False;source.write_text(json.dumps(payload),encoding='utf-8')
        with self.assertRaises(ValidationError):import_licensed_bank(self.folder,source)
        self.assertIsNone(load_bank(self.folder,'../unexpected'))


class StatisticsUITests(RichFixture):
    def app(self):
        self.importer().import_file(self.source);root=tk.Tk();root.attributes('-alpha',0);app=ApplicationWindow(root,controller=self.controller());self.addCleanup(app.close);root.update();return app
    def wait(self,app,condition):
        deadline=time.monotonic()+8
        while not condition() and time.monotonic()<deadline:app.root.update();time.sleep(.01)
        self.assertTrue(condition())
    def test_bottom_stats_entry_is_lazy_local_and_uses_cached_result(self):
        app=self.app();self.assertFalse(hasattr(app,'statistics_panel'));app.nav_note.invoke();app.root.update()
        self.assertEqual(app.current_page,'统计');panel=app.statistics_panel;self.wait(app,lambda:not panel.busy)
        self.assertEqual(panel.data['summary']['total'],4);self.assertIsNone(app.agent_panel.client)
        with patch('wechat_archive.ui.statistics_panel.archive_statistics') as query:
            app.show_page('帮助');app.show_page('统计');app.root.update();query.assert_not_called()
        panel.refresh(True);self.wait(app,lambda:not panel.busy);self.assertTrue(panel.content.winfo_children())
    def test_file_details_and_save_actions_appear_only_after_click(self):
        app=self.app();app.owner_id=1;app.peer_id=self.group(app.controller)['id'];app.load_contacts();app.root.update()
        buttons=[x for x in app.descendants(app.chat_text) if hasattr(x,'attachment_item')]
        self.assertEqual(len(buttons),1);self.assertEqual(buttons[0].cget('text'),'文件')
        self.assertFalse(any(w.winfo_class()=='TButton' and w.cget('text')=='另存附件' for w in app.descendants(app.chat_text)))
        previous=set(app.root.winfo_children());buttons[0].invoke();app.root.update();popup=next(x for x in app.root.winfo_children() if x not in previous and isinstance(x,tk.Toplevel))
        self.assertTrue(any(w.winfo_class()=='TButton' and w.cget('text')=='另存附件' for w in app.descendants(popup)));popup.destroy()
    def test_repeated_contacts_keep_native_widgets_and_selection(self):
        app=self.app();before={key:card[0] for key,card in app.contact_tree.cards.items()};app.load_contacts();app.root.update()
        self.assertEqual(before,{key:card[0] for key,card in app.contact_tree.cards.items()})
        ids=app.contact_tree.get_children();app.contact_tree.set_rows(app.contact_rows,int(ids[-1]));self.assertEqual(app.contact_tree.selection(),(ids[-1],))
    def test_background_completion_releases_busy_before_callback(self):
        app=self.app();panel=app.knowledge_panel;observed=[]
        panel.run(lambda *_:'completed',lambda value:observed.append((value,panel.busy,panel.running)))
        self.wait(app,lambda:bool(observed))
        self.assertEqual(observed,[('completed',False,0)])
    def test_preferred_model_migrates_once_and_preserves_later_choices(self):
        app=self.app();panel=app.agent_panel;models=[{'model':'gpt-6.1-sol','displayName':'GPT-6.1-Sol','isDefault':True,'supportedReasoningEfforts':[{'reasoningEffort':'low'}],'defaultReasoningEffort':'low'},{'model':'unit-other','displayName':'Other'}]
        panel.set_catalog(models);self.assertEqual(panel.selected_model(),'gpt-6.1-sol')
        label=next(k for k,v in panel.model_ids.items() if v=='unit-other');panel.model.set(label);panel.set_catalog(models);self.assertEqual(panel.selected_model(),'unit-other')
        panel.flush_configuration();self.assertTrue(app.controller.settings()['ai']['preferred_model_applied'])
