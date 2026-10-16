"""Codex product workflow checks using the existing fake app-server only."""
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch

import test_agent as agent_fixture


class CodexWorkflowUITests(unittest.TestCase):
    setUp = agent_fixture.AgentPanelTests.setUp
    wait = agent_fixture.AgentPanelTests.wait

    def login(self):
        self.panel.connect()
        self.wait(lambda: not self.panel.busy)
        self.panel.login()
        self.wait(lambda: self.panel.authenticated and not self.panel.busy)

    def test_advanced_component_settings_start_collapsed(self):
        self.assertFalse(self.panel.advanced.expanded)
        self.assertFalse(self.panel.advanced.content.winfo_ismapped())

    def test_connected_without_login_cannot_send(self):
        self.panel.connect()
        self.wait(lambda: not self.panel.busy)
        self.panel.fill_prompt("question")
        self.assertIn("disabled", self.panel.send_button.state())
        self.panel.send()
        self.assertEqual(self.panel.messages, [])
        self.assertEqual(self.panel.input.get("1.0", "end").strip(), "question")
        self.assertIn("登录", self.panel.state.get())

    def test_quick_prompt_only_fills_no_network_or_conversation(self):
        self.panel.fill_prompt("请查找原消息")
        self.assertIsNone(self.panel.client)
        self.assertEqual(self.panel.messages, [])
        self.assertEqual(self.panel.input.get("1.0", "end").strip(), "请查找原消息")

    def test_logged_in_empty_prompt_and_missing_scope_disable_send(self):
        self.login()
        self.panel._controls()
        self.assertIn("disabled", self.panel.send_button.state())
        self.panel.fill_prompt("question")
        self.assertNotIn("disabled", self.panel.send_button.state())
        self.app.owner_id = None
        self.panel._controls()
        self.assertIn("disabled", self.panel.send_button.state())

    def test_control_enter_sends_and_breaks_newline(self):
        self.login()
        self.panel.fill_prompt("核对记录")
        self.assertEqual(self.panel.send_shortcut(), "break")
        self.wait(lambda: not self.panel.active and not self.panel.busy)
        self.assertIn("已查询授权范围", self.panel.transcript.get("1.0", "end"))

    def test_refresh_login_state_does_not_start_turn(self):
        self.login()
        self.panel.refresh_account()
        self.wait(lambda: not self.panel.busy)
        self.assertTrue(self.panel.authenticated)
        self.assertEqual(self.panel.messages, [])

    def test_scope_label_uses_names_and_ids(self):
        self.wait(lambda:'自己（#1）' in self.panel.scope_text.get())
        self.assertIn("自己（#1）", self.panel.scope_text.get())
        self.assertIn("对方（#2）", self.panel.scope_text.get())

    def test_reference_opens_readonly_source_window(self):
        self.login()
        self.panel.fill_prompt("核对记录")
        self.panel.send()
        self.wait(lambda: not self.panel.active and not self.panel.busy)
        before = self.controller.database.read_bytes()
        window = self.panel.open_reference(1)
        self.assertIsNotNone(window)
        self.assertIn("回查", self.panel.state.get())
        window.destroy()
        self.assertEqual(self.controller.database.read_bytes(), before)

    def test_reference_outside_scope_is_not_opened(self):
        self.login()
        self.panel.fill_prompt("核对记录")
        self.panel.send()
        self.wait(lambda: not self.panel.active and not self.panel.busy)
        self.assertIsNone(self.panel.open_reference(999))
        self.assertIn("无法展开", self.panel.state.get())

    def test_scope_change_revokes_old_tools_and_clears_conversation(self):
        self.login()
        self.panel.fill_prompt("核对记录")
        self.panel.send()
        self.wait(lambda: not self.panel.active and not self.panel.busy)
        self.panel.scope.set("当前身份的所有私聊")
        self.wait(lambda: not self.panel.messages and self.panel.client.tools is None)
        self.assertIn("范围已切换", self.panel.state.get())

    def test_copy_preserves_answer_text_and_reference(self):
        self.panel._add("Codex · 回答", "原文\n[消息 #1]")
        with patch.object(self.root, "clipboard_clear") as clear, patch.object(self.root, "clipboard_append") as append:
            self.panel.copy_answer()
        clear.assert_called_once()
        append.assert_called_once_with("原文\n[消息 #1]")

    def test_export_new_file_preserves_scope_and_text(self):
        self.panel._add("你", "question")
        self.panel._add("Codex · 回答", "answer\n[消息 #1]")
        path = self.folder / "conversation.txt"
        with patch("wechat_archive.ui.agent_panel.filedialog.asksaveasfilename", return_value=str(path)):
            self.panel.export_conversation()
        self.assertIn("answer\n[消息 #1]", path.read_text(encoding="utf-8"))
        self.assertIn(self.panel.scope_text.get(), path.read_text(encoding="utf-8"))

    def test_export_existing_file_never_overwritten(self):
        self.panel._add("Codex", "new text")
        path = self.folder / "existing.txt"
        path.write_text("old user text", encoding="utf-8")
        with patch("wechat_archive.ui.agent_panel.filedialog.asksaveasfilename", return_value=str(path)):
            self.panel.export_conversation()
        self.assertEqual(path.read_text(encoding="utf-8"), "old user text")
        self.assertIn("未完成", self.panel.state.get())

    def test_upgrade_copy_is_clickable_and_preserves_original(self):
        original=self.controller.database
        before=original.read_bytes()
        target=self.folder/'升级副本.db'
        with patch('wechat_archive.ui.operation_actions.filedialog.asksaveasfilename',return_value=str(target)):
            self.app.upgrade_button.invoke()
        self.wait(lambda:not self.app.busy)
        self.assertEqual(self.controller.database,target)
        self.assertEqual(original.read_bytes(),before)
        self.assertIn('已验证并打开',self.app.status.get())

    def test_small_window_primary_controls_do_not_overlap(self):
        self.root.geometry('820x600')
        self.app.show_page('Codex 助手')
        self.root.update_idletasks()
        groups=((self.panel.connect_button,self.panel.login_button,self.panel.cancel_login_button),
                (self.panel.logout_button,self.panel.account_button),
                (self.panel.model_box,self.panel.models_button,self.panel.new_button))
        for widgets in groups:
            for left,right in zip(widgets,widgets[1:]):
                self.assertLessEqual(left.winfo_x()+left.winfo_width(),right.winfo_x())


if __name__ == "__main__":
    unittest.main()
