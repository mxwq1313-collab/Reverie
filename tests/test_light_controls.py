"""Screenshot-requested control appearance and genuine Enter/slider behavior."""
import tkinter as tk
import unittest
from unittest.mock import patch
import test_workbench as fixture
from test_codex_controls import CATALOG


class LightControlTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show

    def test_two_filled_search_fields_align_and_submit_on_enter(self):
        self.show(1240,820)
        app=self.app;fields=(app.contact_entry,app.search_entry)
        self.assertEqual([x.placeholder_label.cget('text') for x in fields],['搜索联系人…','搜索聊天记录…'])
        self.assertFalse(app.search_button.winfo_ismapped())
        self.assertEqual(fields[0].winfo_height(),fields[1].winfo_height())
        self.assertAlmostEqual(fields[0].winfo_rooty(),fields[1].winfo_rooty(),delta=2)
        self.assertAlmostEqual(app.contact_tree.winfo_rooty(),app.chat_text.winfo_rooty(),delta=2)
        self.assertTrue(all(x.cget('style')=='Search.TEntry' for x in fields))
        app.contact_entry.focus_force();app.contact_keyword.set('第二会话');app.contact_entry.event_generate('<Return>');self.root.update()
        self.assertEqual([x['nickname'] for x in app.contact_rows],['第二会话'])
        app.contact_keyword.set('');app.contact_entry.event_generate('<Return>');self.root.update()
        app.search_word.set('论文修改');app.search_entry.focus_force();app.search_entry.event_generate('<Return>');self.root.update()
        self.assertGreater(app.message_total,0);self.assertTrue(all('论文修改' in row['content'] for row in app.message_rows))

    def test_time_labels_do_not_repeat_timezone_but_keep_correct_hour(self):
        self.show();app=self.app
        self.assertNotIn('UTC',app.chat_subtitle.get())
        first=app.chat_text.bubbles[1]['label'].cget('text');self.assertIn('08:00:00',first);self.assertNotIn('UTC',first)
        self.assertTrue(app.message_rows[0]['create_time'].endswith('+00:00') or app.message_rows[0]['create_time'].endswith('Z'))

    def test_power_card_is_frameless_compact_and_uses_supported_efforts(self):
        self.show();panel=self.app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
        popup=panel.parameters_popup;view=panel.power_popover
        self.assertTrue(popup.overrideredirect());self.assertLessEqual(popup.winfo_width(),self.app.theme.u(340))
        self.assertTrue(panel.power_slider.winfo_ismapped());self.assertTrue(panel.power_model_button.winfo_ismapped())
        view.choose(len(view.levels())-1);self.assertEqual(panel.selected_effort(),'ultra')
        panel.model.set('隐藏测试模型 · unit-hidden');self.root.update();self.assertEqual(view.levels(),['练气'])
        view.choose(100);self.assertEqual(panel.selected_effort(),'low')
        self.assertFalse(hasattr(view,'reset_button'));self.assertFalse(hasattr(view,'reset'))
        self.root.event_generate('<Button-1>',x=5,y=5);self.root.update();self.assertFalse(popup.winfo_ismapped())
        self.assertEqual(self.errors,[])

    def test_model_chip_and_sparkles_stop_when_card_closes(self):
        self.show();panel=self.app.agent_panel;self.app.ui_settings['reduce_motion']=False
        self.assertEqual(panel.parameter_caption.get(),'选择模型')
        panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
        view=panel.power_popover;view.choose(len(view.levels())-1);self.root.update()
        self.assertIsNotNone(view.animation_job);self.assertTrue(view.slider.find_withtag('sparkle'))
        first=[view.slider.coords(item) for item in view.slider.find_withtag('sparkle')]
        self.root.after(120,self.root.quit);self.root.mainloop();self.root.update()
        self.assertNotEqual(first,[view.slider.coords(item) for item in view.slider.find_withtag('sparkle')])
        view.stop_effect();self.app.ui_settings['reduce_motion']=True
        with patch.object(self.root,'after',wraps=self.root.after) as schedule:
            phase=view.phase;view.animate();schedule.assert_not_called();self.assertEqual(view.phase,phase)
        panel.parameters_popup.withdraw();self.root.update();self.assertIsNone(view.animation_job)
        panel.parameters_button.invoke();self.root.update();self.assertIsNone(view.animation_job)
        self.app.ui_settings['reduce_motion']=False;view.start_effect();self.root.update();self.assertIsNotNone(view.animation_job)
        panel.parameters_popup.destroy();self.root.update();self.assertIsNone(view.animation_job)
        self.assertEqual(self.errors,[])

    def test_model_chip_shows_selected_model_with_centered_image_arrow(self):
        from wechat_archive.ui.model_controls import AUTO_MODEL
        self.show();panel=self.app.agent_panel;panel.set_catalog(CATALOG);self.root.update()
        self.assertEqual(panel.parameter_caption.get(),'测试主模型')
        self.assertEqual(str(panel.parameters_button.cget('compound')),'right')
        self.assertTrue(panel.parameters_button.cget('image'))
        self.assertNotIn('⌄',panel.parameter_caption.get())
        panel.model.set('隐藏测试模型 · unit-hidden');self.root.update()
        self.assertEqual(panel.parameter_caption.get(),'隐藏测试模型')
        panel.model.set(AUTO_MODEL);self.root.update()
        self.assertEqual(panel.parameter_caption.get(),'测试主模型')
        self.app.theme.update(24,self.app.theme.family,'dark','zh_CN',48);self.show(820,600)
        panel.refresh_parameter_caption();self.root.update()
        self.assertEqual(panel.parameters_button.arrow_image.height(),self.app.theme.u(14))
        self.assertLessEqual(panel.parameters_button.winfo_rootx()+panel.parameters_button.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())
        self.assertEqual(self.errors,[])

    def test_tool_progress_uses_readable_completion_and_failure_text(self):
        self.show();panel=self.app.agent_panel
        from wechat_archive.ui.task_status import TOOL_STATUS,tool_status
        for name,pair in TOOL_STATUS.items():
            for success,expected in ((True,pair[0]),(False,pair[1])):
                self.root.after_cancel(panel.poll_job)
                panel.events.put({'generation':panel.generation,'kind':'tool','name':name,'success':success});panel.poll()
                self.assertEqual(panel.state.get(),expected);self.assertNotIn('archive_',panel.state.get())
        self.assertEqual(tool_status('unknown_private_tool',True),'已完成资料读取')
        self.assertEqual(tool_status(None,False),'资料读取未完成')
        self.app.localizer.language='en_US';self.root.after_cancel(panel.poll_job)
        panel.events.put({'generation':panel.generation,'kind':'tool','name':'archive_messages','success':True});panel.poll()
        self.assertEqual(panel.state.get(),'Chat history search complete')
        self.assertEqual(self.errors,[])

    def test_search_and_card_survive_theme_font_and_small_window(self):
        app=self.app
        for width,height,mode,size in ((820,600,'dark',24),(1240,820,'green',15)):
            app.theme.update(size,app.theme.family,mode,'zh_CN',48);self.show(width,height)
            self.assertAlmostEqual(app.contact_entry.winfo_rooty(),app.search_entry.winfo_rooty(),delta=2)
            self.assertEqual(app.contact_entry.winfo_height(),app.search_entry.winfo_height())
            panel=app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
            popup=panel.parameters_popup
            self.assertLessEqual(popup.winfo_rootx()+popup.winfo_width(),self.root.winfo_screenwidth())
            self.assertGreaterEqual(popup.winfo_rooty(),0);self.assertGreater(panel.power_slider.winfo_height(),20);popup.withdraw()
        self.assertEqual(self.errors,[])

    def test_combobox_has_a_light_image_chevron_and_keeps_native_selection(self):
        self.show();layout=str(self.app.theme.style.layout('TCombobox'))
        self.assertNotIn("'Combobox.downarrow'",layout);self.assertIn('.downarrow',layout)
        current=self.app.owner_box.current();self.app.owner_box.current(current);self.app.owner_box.event_generate('<<ComboboxSelected>>');self.root.update()
        self.assertIsNotNone(self.app.owner_id);self.assertEqual(self.errors,[])

    def test_native_popdown_focus_closes_card_without_python_widget_lookup(self):
        self.show();panel=self.app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
        box=self.app.search_box
        self.root.tk.call('ttk::combobox::Post',str(box));self.root.update()
        panel.power_popover.hide_if_outside();self.root.update()
        self.root.tk.call('ttk::combobox::Unpost',str(box))
        self.assertFalse(panel.parameters_popup.winfo_ismapped());self.assertEqual(self.errors,[])

    def test_card_destroy_removes_only_its_global_click_handler(self):
        self.show();panel=self.app.agent_panel;calls=[]
        other=self.root.bind_all('<Button-1>',lambda _:calls.append(True),add='+')
        own=panel.power_popover.outside_binding
        self.assertIn(own,self.root.bind_all('<Button-1>'))
        panel.parameters_popup.destroy();self.root.update()
        self.assertNotIn(own,self.root.bind_all('<Button-1>'))
        self.assertIn(other,self.root.bind_all('<Button-1>'))
        self.assertFalse(self.root.tk.call('info','commands',own))
        self.root.event_generate('<Button-1>',x=5,y=5);self.root.update()
        self.assertTrue(calls);self.assertEqual(self.errors,[])

    def test_name_only_brand_and_six_realms_keep_provider_effort_values(self):
        from wechat_archive.branding import window_title
        self.show();app=self.app;panel=app.agent_panel
        self.assertEqual(self.root.title(),'思绪');self.assertEqual(app.brand_label.cget('text'),'思绪')
        self.assertEqual(window_title('en_US'),'Sixu')
        values=('low','medium','high','xhigh','max','ultra')
        names=('练气','筑基','金丹','元婴','化神','渡劫')
        panel.set_catalog([{'model':'unit-realms','displayName':'测试境界','isDefault':True,'defaultReasoningEffort':'medium',
                            'supportedReasoningEfforts':[{'reasoningEffort':x} for x in values]}])
        panel.model.set('测试境界 · unit-realms');panel.parameters_button.invoke();self.root.update()
        view=panel.power_popover;self.assertEqual(tuple(view.levels()),names)
        for index,(name,value) in enumerate(zip(names,values)):
            view.choose(index);self.root.update()
            self.assertEqual(view.title.cget('text'),name);self.assertEqual(panel.selected_effort(),value)
        panel.flush_configuration();self.assertEqual(app.controller.settings()['ai']['effort'],'ultra')
        self.assertEqual(self.errors,[])
