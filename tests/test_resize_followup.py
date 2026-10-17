"""Native sizing, split persistence and absence of floating operation notices."""
import contextlib,time,unittest
from types import SimpleNamespace
from unittest.mock import patch
from wechat_archive.errors import ValidationError
import test_workbench as fixture

class ResizeFollowupTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self):
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            self.root.update()
            if not self.app.layout_job and not self.app.chat_text.layout_job and not self.app.chat_text.reflow_busy:break
            time.sleep(.01)
        self.root.update();self.assertFalse(self.app.layout_job);self.assertEqual(self.errors,[])
    @contextlib.contextmanager
    def sizing(self):
        try:yield self.app
        finally:self.settle()
    def test_all_operation_feedback_is_status_only(self):
        self.show();app=self.app
        for text in ('正在只读连接并核验账号，加载联系人…','正在导入…','操作已完成。','请选择会话。','读取未完成。'):
            app.feedback.show(text);app.feedback.receipt('任意操作','旧状态');self.root.update()
            self.assertEqual(app.status.get(),text);self.assertFalse(hasattr(app.feedback,'frame'))
        self.assertTrue(app.status_label.winfo_ismapped());self.assertEqual(self.errors,[])
    def test_hover_hint_has_transparent_outer_corners(self):
        self.show();button=self.app.capsule_button;button.show_tip();self.root.update();tip=button._action_hint.tip
        self.assertTrue(tip.overrideredirect());self.assertEqual(tip.attributes('-transparentcolor'),'#fe00fe')
        self.assertEqual(tip.cget('background'),'#fe00fe');button.hide_tip();self.assertIsNone(button._action_hint.tip)
    def test_hover_hint_does_not_drain_idle_and_can_be_cancelled_before_mapping(self):
        self.show();button=self.app.capsule_button;hint=button._action_hint
        with patch.object(self.root,'update_idletasks',side_effect=AssertionError('nested idle drain')), patch('tkinter.Misc.update_idletasks',side_effect=AssertionError('nested idle drain')):
            hint.show();hint.hide();self.root.update()
        self.assertIsNone(hint.tip);self.assertIsNone(hint.layout_job);self.assertEqual(self.errors,[])

    def test_contacts_width_is_persisted_and_not_reset_by_window_resize(self):
        self.show(1450,850);self.settle();app=self.app;panes=app.browser_panes
        panes.sash_place(0,340,0);app.save_browser_sash();self.root.update();self.assertEqual(app.controller.browser_layout()['width'],340)
        self.root.geometry('1300x800');self.settle();self.assertAlmostEqual(app.conversation_column.winfo_width(),340,delta=2)
        app.show_page('工具与设置');app.show_page('聊天归档');self.settle();self.assertEqual(app.contacts_width,340)
    def test_keyboard_split_resize_and_reset(self):
        self.show(1450,850);self.settle();app=self.app;panes=app.browser_panes
        before=panes.sash_coord(0)[0];panes.focus_force();panes.event_generate('<Right>');self.root.update()
        self.assertAlmostEqual(panes.sash_coord(0)[0],before+app.theme.u(24),delta=2)
        panes.event_generate('<Home>');self.root.update();self.assertEqual(app.controller.browser_layout()['width'],270)
        self.assertTrue(bool(int(panes.cget('opaqueresize'))))
    def test_narrow_splits_keep_toolbar_and_load_more_inside_their_columns(self):
        self.show(1500,850);app=self.app;app.theme.update(24,app.theme.family,'dark','zh_CN',48);self.settle()
        app.browser_panes.sash_place(0,1,0);app.save_browser_sash();self.root.update();app.layout_browser_split();self.root.update()
        column=app.conversation_column;button=app.avatar_refresh_button
        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),column.winfo_rootx()+column.winfo_width())
        app.browser_panes.sash_place(0,app.browser_panes.winfo_width()-1,0);app.save_browser_sash();self.root.update();app.fit_chat_footer();self.root.update()
        button=app.more_button;column=app.message_content_column
        self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),column.winfo_rootx()+column.winfo_width())
        self.assertEqual(self.errors,[])

    def test_copilot_width_can_exceed_previous_640_limit(self):
        self.show(1800,900);self.settle();app=self.app;panes=app.workspace_panes
        panes.sash_place(0,panes.winfo_width()-app.theme.u(800)-int(panes.cget('sashwidth')),0);app.save_copilot_sash();self.root.update()
        self.assertAlmostEqual(app.controller.copilot_layout()['width'],800,delta=2)
        app.layout_key=None;app.adapt_layout();self.root.update();self.assertAlmostEqual(app.copilot_host.winfo_width(),800,delta=3)
    def test_maximize_restore_keeps_copilot_preferred_width(self):
        self.show(1800,850);self.settle();app=self.app
        app.copilot_width=360;app.layout_key=None;app.adapt_layout();self.root.update()
        for state in ('zoomed','normal'):
            self.root.state(state);self.root.update();self.settle()
            self.assertAlmostEqual(app.copilot_host.winfo_width(),app.theme.u(360),delta=3)
        self.assertEqual(self.errors,[])

    def test_drawer_drag_updates_real_geometry_and_commits_once(self):
        self.show(900,700);self.settle();app=self.app;before=app.copilot_host.winfo_width()
        app.start_copilot_drag(SimpleNamespace(x_root=600));app.drag_copilot(SimpleNamespace(x_root=550));self.root.update()
        self.assertGreater(app.copilot_host.winfo_width(),before);self.assertFalse(app.copilot_guide.winfo_ismapped())
        self.assertEqual(app.controller.copilot_layout()['width'],360)
        app.finish_copilot_drag();self.root.update();self.assertFalse(app.copilot_guide.winfo_ismapped());self.assertEqual(app.controller.copilot_layout()['width'],410)
        app.copilot_grip.focus_force();app.copilot_grip.event_generate('<Right>');self.root.update()
        self.assertEqual(app.controller.copilot_layout()['width'],386)
        app.copilot_grip.event_generate('<Home>');self.root.update();self.assertEqual(app.copilot_width,360)
    def test_live_resize_tracks_viewport_without_unmapping_workspace(self):
        self.show(1260,820);self.app.show_page('随机回忆');self.settle();app=self.app
        unmaps=[];app.workspace_panes.bind('<Unmap>',lambda e:unmaps.append(e.widget),add='+')
        identity=str(app.toolbox_panel.random.memory)
        for geometry in ('1100x740','1450x850','980x700'):
            self.root.geometry(geometry);self.root.update()
            self.assertTrue(app.workspace_panes.winfo_viewable())
            self.assertAlmostEqual(app.workspace_panes.winfo_width(),app.resize_viewport.winfo_width(),delta=1)
            self.assertAlmostEqual(app.workspace_panes.winfo_height(),app.resize_viewport.winfo_height(),delta=1)
        self.assertEqual(unmaps,[]);self.assertEqual(str(app.toolbox_panel.random.memory),identity)
        self.assertFalse(hasattr(app,'native_resize'));self.assertEqual(self.errors,[])

    def test_resize_notifications_coalesce_and_moving_does_not_queue_layout(self):
        self.show(1260,820);self.settle();app=self.app
        event=SimpleNamespace(widget=self.root,width=1200,height=800)
        with patch.object(self.root,'after_idle',wraps=self.root.after_idle) as schedule:
            app.schedule_layout(event);job=app.layout_job
            for width in range(1201,1250):
                event.width=width;app.schedule_layout(event)
            self.assertEqual(app.layout_job,job);self.assertEqual(schedule.call_count,1)
        self.settle()
        event.width,event.height=app.resize_event_size
        app.schedule_layout(event);self.assertIsNone(app.layout_job)

    def test_live_resize_preserves_unicode_selection_and_widget(self):
        self.show(1260,820);app=self.app;app.show_page('随机回忆');self.settle();text=app.toolbox_panel.random.memory
        raw='原文😀 hello\n保留全部换行';text.configure(state='normal');text.delete('1.0','end');text.insert('1.0',raw);text.tag_add('sel','1.0','1.2');text.configure(state='disabled');identity=str(text)
        for geometry in ('980x700','1450x850','1100x760'):self.root.geometry(geometry);self.root.update()
        self.assertEqual(str(text),identity);self.assertEqual(text.get('1.0','end-1c'),raw);self.assertEqual(text.get('sel.first','sel.last'),'原文')

    def test_height_only_resize_keeps_memory_live_and_selection(self):
        self.show(1260,820);self.app.show_page('随机回忆');self.settle();text=self.app.toolbox_panel.random.memory
        text.tag_add('sel','1.0','1.2');before=text.winfo_height();self.root.geometry('1260x650');self.root.update()
        self.assertLess(text.winfo_height(),before);self.assertTrue(text.winfo_viewable());self.assertEqual(self.errors,[])

    def test_fast_mode_has_purple_icon_and_flow_without_changing_effort(self):
        from test_codex_controls import CATALOG
        self.show();self.app.ui_settings['reduce_motion']=False;panel=self.app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
        view=panel.power_popover;panel.fast_mode.set(True);self.root.update();effort=panel.effort.get();thumb=view.slider.coords('thumb')
        self.assertEqual(panel.fast_button.icon_key[1],'#8b5cf6');self.assertTrue(view.slider.find_withtag('fast_flow'))
        first=view.slider.coords(view.slider.find_withtag('fast_flow')[0]);view.stop_effect();view.animate()
        self.assertNotEqual(view.slider.coords(view.slider.find_withtag('fast_flow')[0]),first)
        self.assertEqual(panel.effort.get(),effort);self.assertEqual(view.slider.coords('thumb'),thumb)
        panel.fast_mode.set(False);self.root.update();self.assertNotEqual(panel.fast_button.icon_key[1],'#8b5cf6')
        self.assertFalse(view.slider.find_withtag('fast_flow'));self.assertIsNone(view.animation_job)
    def test_fast_effect_stops_when_hidden_and_respects_reduced_motion(self):
        from test_codex_controls import CATALOG
        self.show();self.app.ui_settings['reduce_motion']=False;panel=self.app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update();view=panel.power_popover
        panel.fast_mode.set(True);self.root.update();self.assertIsNotNone(view.animation_job)
        panel.parameters_popup.withdraw();self.root.update();self.assertIsNone(view.animation_job)
        self.app.ui_settings['reduce_motion']=True;panel.parameters_button.invoke();self.root.update();self.assertIsNotNone(view.animation_job)
        self.assertTrue(view.slider.find_withtag('fast_pulse'));self.assertFalse(view.slider.find_withtag('fast_flow'))
        first=view.slider.coords(view.slider.find_withtag('fast_pulse')[0]);view.stop_effect();view.animate()
        self.assertEqual(first,view.slider.coords(view.slider.find_withtag('fast_pulse')[0]))
        self.assertTrue(self.app.ui_settings['reduce_motion'])
    def test_repeated_icon_refresh_does_not_invalidate_padding(self):
        self.show();button=self.app.copilot_button;button.refresh_icon()
        with patch.object(button,'configure',wraps=button.configure) as configure:
            button.refresh_icon();button.refresh_icon();self.assertEqual(configure.call_count,0)

    def test_layout_preferences_reject_non_numeric_and_keep_wide_values(self):
        controller=self.app.controller;settings=controller.settings();settings['browser_layout']={'width':True};controller.save_settings(settings)
        self.assertEqual(controller.browser_layout()['width'],270)
        controller.save_browser_layout(500);controller.save_copilot_layout(True,1200)
        self.assertEqual(controller.browser_layout()['width'],500);self.assertEqual(controller.copilot_layout()['width'],1200)
        for value in (True,-1,5000,'wide'):
            with self.assertRaises(ValidationError):controller.save_browser_layout(value)

if __name__=='__main__':unittest.main(verbosity=2)
