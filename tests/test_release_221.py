"""2.2.1 utility workflows on a synthetic archive and real native widgets."""
import hashlib,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
import test_workbench as fixture


class Release221Tests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    wait=fixture.WorkbenchTests.wait

    def open(self):
        self.show();self.app.memory_button.invoke();self.root.update()
        return self.app.toolbox_panel.random

    def test_bottom_symbol_opens_nonmodal_utility_without_changing_page(self):
        app=self.app;before=self.path.read_bytes();tool=self.open()
        self.assertEqual(app.current_page,'聊天归档');self.assertNotIn('随机回忆',app.tab_routes)
        self.assertEqual(len(app.tools_notebook.tabs()),3)
        self.assertTrue(app.memory_popup.window.winfo_viewable());self.assertTrue(tool.memory.winfo_ismapped())
        self.assertEqual(str(app.memory_button.cget('compound')),'image');self.assertEqual(app.memory_button.cget('text'),'随机回忆')
        self.assertLess(app.memory_button.winfo_y(),app.capsule_button.winfo_y())
        self.assertEqual(len({app.memory_button.icon,app.capsule_button.icon,app.nav_note.icon}),3)
        self.assertIsNone(self.root.grab_current());self.assertFalse(tool.filters.winfo_ismapped())
        self.assertEqual(self.path.read_bytes(),before);self.assertEqual(self.errors,[])

    def test_detection_progress_never_creates_floating_receipt(self):
        self.show();app=self.app;gate=threading.Event();called=[]
        def discover(root):
            called.append(root);gate.wait(3)
            return {'root':'synthetic','accounts':[],'client_version':'synthetic'}
        with patch.object(app.controller,'discover',side_effect=discover):
            before=app.status.get();app.detect_source()
            try:
                app.feedback.receipt('检测账号',before);self.root.update()
                self.assertTrue(app.busy);self.assertIn('正在检测',app.status.get())
                self.assertFalse(app.feedback.frame.winfo_ismapped())
            finally:gate.set();self.wait()
        self.assertEqual(len(called),1);self.assertEqual(app.status.get(),'账号检测完成。')
        app.feedback.show('操作已完成。');self.root.update();self.assertTrue(app.feedback.frame.winfo_ismapped())

    def test_filter_draw_history_copy_save_and_original_use_actual_archive(self):
        tool=self.open();before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        tool.toggle_filters();self.root.update();self.assertTrue(tool.filters.winfo_ismapped())
        tool.start.set('2026-10-10');tool.end.set('2026-10-10');tool.keyword.set('论文修改')
        tool.search();self.wait();self.assertEqual(tool.total,1);self.assertEqual(tool.row['id'],8)
        tool.copy();self.assertIn('论文修改',self.root.clipboard_get());self.assertIn('[消息 #8]',self.root.clipboard_get())
        output=self.folder/'memory.txt'
        with patch('wechat_archive.ui.toolbox_panel.filedialog.asksaveasfilename',return_value=str(output)):tool.save()
        self.assertEqual(output.read_text(encoding='utf-8'),self.root.clipboard_get())
        saved=tool.row;tool.search();self.wait();self.assertEqual(tool.row,saved)
        self.assertIn('全部打捞',self.app.status.get())
        tool.open_original();self.root.update();self.assertEqual(self.app.current_page,'聊天归档')
        self.assertFalse(self.app.memory_popup.window.winfo_viewable());self.assertIn('消息 #8',self.app.chat_subtitle.get())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(),before);self.assertEqual(self.errors,[])

    def test_popup_close_reopen_retains_history_and_navigation_buttons_work(self):
        tool=self.open();tool.search();self.wait();first=tool.row['id'];tool.search();self.wait();second=tool.row['id']
        self.assertNotEqual(first,second);self.assertNotIn('disabled',tool.previous.state())
        tool.previous.invoke();self.root.update();self.assertEqual(tool.row['id'],first)
        self.assertIn('disabled',tool.previous.state());tool.next.invoke();self.assertEqual(tool.row['id'],second)
        widget=str(tool.memory);self.app.memory_button.invoke();self.root.update();self.assertFalse(self.app.memory_popup.window.winfo_viewable())
        self.app.memory_button.invoke();self.root.update();self.assertEqual(str(tool.memory),widget);self.assertEqual(tool.row['id'],second)
        tool.clear_history();self.assertEqual(tool.history,[]);self.assertIn('disabled',tool.result_buttons[0].state())

    def test_scope_change_revokes_old_memory_and_errors_are_inline(self):
        tool=self.open();tool.search();self.wait();self.app.memory_popup.hide()
        self.app.peer_id=3;self.app.memory_popup.open();self.root.update()
        self.assertIsNone(tool.row);self.assertEqual(tool.history,[]);self.assertNotIn('记录 ',tool.memory.get('1.0','end'))
        self.assertIn('disabled',tool.result_buttons[1].state())
        tool.start.set('not-a-date');tool.search();self.assertIn('YYYY-MM-DD',tool.summary.get())
        self.assertFalse(self.app.busy);self.assertEqual(self.errors,[])

    def test_large_text_and_narrow_window_keep_actions_inside_popup(self):
        self.show(900,700);app=self.app;app.theme.update(24,app.theme.family,'dark','zh_CN',48)
        app.memory_popup.open();self.root.update();tool=app.toolbox_panel.random;tool.toggle_filters()
        for _ in range(4):self.root.update();time.sleep(.01)
        window=app.memory_popup.window
        for button in (tool.search_button,tool.filter_button,tool.previous,*tool.result_buttons):
            self.assertTrue(button.winfo_ismapped())
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),window.winfo_rootx()+window.winfo_width()+2)
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),window.winfo_rooty()+window.winfo_height()+2)
        self.assertEqual(self.errors,[])


if __name__=='__main__':unittest.main(verbosity=2)
