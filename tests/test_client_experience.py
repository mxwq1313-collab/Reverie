"""First client-experience batch, using synthetic archives and fake model services."""
import unittest
from unittest.mock import patch
import test_workbench as workbench_fixture


class CapabilityUITests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    wait=workbench_fixture.WorkbenchTests.wait

    def test_basic_archive_displays_actual_limits_and_upgrade_action(self):
        before=self.path.read_bytes()
        self.assertIn('100000',self.app.source_capability_text.get())
        self.assertNotIn('disabled',self.app.source_upgrade_button.state())
        self.assertFalse(self.controller.source_capabilities()['streaming'])
        self.assertEqual(before,self.path.read_bytes())

    def test_upgrade_action_switches_description_and_keeps_original(self):
        before=self.path.read_bytes();target=self.folder/'extended.db'
        with patch('wechat_archive.ui.operation_actions.filedialog.askopenfilename',return_value=str(self.path)):
            self.app.source_upgrade_button.invoke()
        self.wait()
        self.assertTrue(self.controller.source_capabilities()['streaming'])
        self.assertIn('分批',self.app.source_capability_text.get())
        self.assertNotIn('最多 100000',self.app.source_capability_text.get())
        self.assertNotIn('disabled',self.app.source_upgrade_button.state())
        self.assertEqual(before,self.path.read_bytes())
        self.controller.open_archive(self.path);self.app.refresh_archive()
        self.assertIn('基础归档',self.app.source_capability_text.get())

    def test_no_archive_does_not_create_one_to_describe_capabilities(self):
        from wechat_archive.ui.application_controller import ApplicationController
        controller=ApplicationController(self.folder/'empty')
        self.assertIn('请先打开',controller.source_capabilities()['description'])
        self.assertFalse((controller.data_dir/'chat.db').exists())

    def test_unavailable_archive_does_not_display_unverified_capability(self):
        with patch.object(self.controller,'source_capabilities',side_effect=OSError('unit unavailable')):
            self.app.update_source_capabilities()
        self.assertIn('未确认',self.app.source_capability_text.get())
        self.assertNotIn('disabled',self.app.source_upgrade_button.state())


class SearchReturnUITests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    show=workbench_fixture.WorkbenchTests.show
    add_bulk=workbench_fixture.WorkbenchTests.add_bulk

    def search_all(self):
        self.app.search_scope.set('全部会话');self.app.search_word.set('论文修改')
        self.app.start_date.set('2026-10-09');self.app.end_date.set('2026-10-10');self.app.load_messages()

    def test_return_restores_scope_filters_rows_and_target_conversation(self):
        self.search_all();before=list(self.app.message_rows);peer=self.app.peer_id
        self.app.show_context(self.second);self.assertIsNotNone(self.app.search_return_state)
        self.app.return_results_button.invoke()
        self.assertEqual(self.app.message_rows,before);self.assertEqual(self.app.peer_id,peer)
        self.assertEqual(self.app.search_scope.get(),'全部会话');self.assertEqual(self.app.search_word.get(),'论文修改')
        self.assertEqual((self.app.start_date.get(),self.app.end_date.get()),('2026-10-09','2026-10-10'))
        self.assertIsNone(self.app.search_return_state)

    def test_return_keeps_loaded_pages_and_pixel_reading_position(self):
        self.add_bulk();self.app.search_scope.set('全部会话');self.app.search_word.set('记录');self.app.load_messages()
        self.app.load_messages(more=True);self.show();canvas=self.app.chat_text.canvas;canvas.yview_moveto(.15);self.root.update()
        before=canvas.canvasy(0);rows=list(self.app.message_rows)
        self.app.show_context(rows[110]['id']);self.root.update();self.app.return_search_results();self.root.update()
        self.assertEqual(self.app.message_rows,rows);self.assertAlmostEqual(canvas.canvasy(0),before,delta=5)

    def test_changed_archive_revokes_cached_search_results(self):
        self.search_all();self.app.show_context(self.second)
        self.service.update_message(1,content='changed synthetic record')
        self.app.return_search_results()
        self.assertIn('旧搜索结果已撤销',self.app.status.get());self.assertIsNone(self.app.search_return_state)
        self.assertEqual(self.app.peer_id,3)

    def test_explicit_contact_change_or_new_search_discards_return_state(self):
        self.search_all();self.app.show_context(self.second);self.app.load_messages()
        self.assertIsNone(self.app.search_return_state)
        self.search_all();self.app.show_context(self.second);self.app.contact_tree.selection_set('2');self.app.select_contact()
        self.assertIsNone(self.app.search_return_state)

    def test_failed_context_does_not_destroy_search(self):
        self.search_all();before=list(self.app.message_rows)
        self.app.show_context(99999)
        self.assertEqual(self.app.message_rows,before);self.assertEqual(self.app.search_word.get(),'论文修改')

    def test_source_change_between_pages_cannot_relabel_old_rows_as_current(self):
        self.add_bulk();self.app.search_scope.set('全部会话');self.app.search_word.set('记录');self.app.load_messages()
        old_token=self.app.loaded_token;before=list(self.app.message_rows)
        self.service.update_message(1,content='changed between pages')
        self.app.load_messages(more=True)
        self.assertEqual(self.app.loaded_token,old_token);self.assertEqual(self.app.message_rows,before)
        self.assertIn('不能追加旧分页',self.app.status.get())
        self.app.show_context(self.second);self.app.return_search_results()
        self.assertIn('旧搜索结果已撤销',self.app.status.get())
