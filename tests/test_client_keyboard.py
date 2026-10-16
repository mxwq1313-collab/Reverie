"""Keyboard events are delivered to isolated Tk widgets, not the user's desktop."""
import unittest
import test_workbench as workbench_fixture


class KeyboardWorkflowTests(unittest.TestCase):
    setUp=workbench_fixture.WorkbenchTests.setUp
    show=workbench_fixture.WorkbenchTests.show

    def test_arrow_selection_and_enter_open_actual_conversation(self):
        self.show();canvas=self.app.contact_tree.canvas;canvas.focus_force();self.root.update()
        prior=self.app.peer_id;keys=self.app.contact_tree.get_children()
        canvas.event_generate('<Down>');self.root.update()
        self.assertEqual(self.app.contact_tree.selection(),(keys[1],));self.assertEqual(self.app.peer_id,prior)
        canvas.event_generate('<Return>');self.root.update()
        self.assertEqual(self.app.peer_id,int(keys[1]));self.assertEqual(self.app.message_rows[0]['id'],self.second)
        self.assertEqual(int(canvas['takefocus']),1);self.assertEqual(int(canvas['highlightthickness']),0)

    def test_ctrl_f_and_global_search_shortcut_use_real_bindings(self):
        self.show();canvas=self.app.contact_tree.canvas;canvas.focus_force();self.root.update()
        canvas.event_generate('<Control-f>');self.root.update();self.assertIs(self.root.focus_get(),self.app.search_entry)
        self.app.search_entry.event_generate('<Control-Shift-F>');self.root.update()
        self.assertEqual(self.app.search_scope.get(),'全部会话')

    def test_escape_clears_filter_and_alt_left_returns_search(self):
        self.show();self.app.search_scope.set('全部会话');self.app.search_word.set('论文修改');self.app.load_messages()
        self.app.show_context(self.second);self.root.update();self.app.search_entry.focus_force()
        self.app.search_entry.event_generate('<Alt-Left>');self.root.update()
        self.assertEqual(self.app.search_word.get(),'论文修改');self.assertEqual(self.app.message_total,2)
        self.app.search_entry.event_generate('<Escape>');self.root.update()
        self.assertEqual(self.app.search_word.get(),'');self.assertEqual(self.app.message_total,16)

    def test_empty_list_navigation_is_safe_and_shortcuts_do_not_intercept_assistant(self):
        self.app.contact_tree.set_rows([])
        self.assertEqual(self.app.contact_tree.move_selected(1),'break')
        self.assertEqual(self.app.contact_tree.activate_selected(),'break')
        self.app.show_page('Codex 助手');self.app.agent_panel.input.insert('1.0','draft')
        self.assertIsNone(self.app.browser_escape());self.assertIsNone(self.app.focus_message_search())
        self.assertEqual(self.app.agent_panel.input.get('1.0','end').strip(),'draft')

    def test_home_end_clamp_without_activating_until_enter(self):
        self.show();keys=self.app.contact_tree.get_children();prior=self.app.peer_id
        self.app.contact_tree.move_selected(100);self.assertEqual(self.app.contact_tree.selection(),(keys[-1],))
        self.app.contact_tree.move_selected(-100);self.assertEqual(self.app.contact_tree.selection(),(keys[0],))
        self.assertEqual(self.app.peer_id,prior)
