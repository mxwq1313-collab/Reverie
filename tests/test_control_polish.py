"""Cross-page native control geometry, dropdown behavior and bounded rendering work."""
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import test_workbench as fixture
from test_codex_controls import CATALOG
from wechat_archive.ui.search_entry import SearchEntry
from wechat_archive.ui.theme import PAPER,SELECTED


class ControlPolishTests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show

    def test_field_geometry_and_action_alignment_across_sizes(self):
        app=self.app
        for size,width,height,mode in ((15,1240,820,'green'),(24,820,600,'dark')):
            app.theme.update(size,app.theme.family,mode,'zh_CN',48);self.show(width,height);app.show_page('电脑微信');self.root.update()
            fields=(app.account_box,app.source_contact_entry)
            self.assertLessEqual(abs(fields[0].winfo_height()-fields[1].winfo_height()),2)
            for left,right in ((app.account_box,app.detect_button),(app.source_contact_entry,app.load_source_button)):
                self.assertAlmostEqual(left.winfo_rooty()+left.winfo_height()/2,right.winfo_rooty()+right.winfo_height()/2,delta=1)
                self.assertLessEqual(abs(left.winfo_height()-right.winfo_height()),2)
            entry=app.theme.style.layout('TEntry')[0][0]
            self.assertEqual(entry,app.theme.style.layout('Search.TEntry')[0][0])
            self.assertIn(entry,str(app.theme.style.layout('TCombobox')))
        self.assertEqual(self.errors,[])

    def test_native_dropdown_restyles_existing_popup_and_keeps_postcommand(self):
        self.show();app=self.app;box=app.owner_box
        for mode in ('green','dark','light'):
            app.theme.update(17,app.theme.family,mode,'zh_CN',48);self.root.update()
            try:
                self.root.tk.call('ttk::combobox::Post',str(box));self.root.update()
                pop=str(self.root.tk.call('ttk::combobox::PopdownWindow',str(box)))+'.f.l'
                self.assertEqual(str(self.root.tk.call(pop,'cget','-background')),app.theme.palette['PAPER'])
                self.assertEqual(str(self.root.tk.call(pop,'cget','-selectbackground')),app.theme.palette['SELECTED'])
            finally:self.root.tk.call('ttk::combobox::Unpost',str(box))
        calls=[];extra=ttk.Combobox(self.root,values=('A','B'),postcommand=lambda:calls.append(True))
        app.theme.scope_font(extra,'TCombobox')
        for _ in range(2):
            self.root.tk.call(str(extra),'cget','-postcommand')
            extra.tk.call('eval',extra.cget('postcommand'))
        self.assertEqual(calls,[True,True]);extra.destroy();self.assertEqual(self.errors,[])

    def test_search_surfaces_are_shared_without_changing_live_filters(self):
        self.show();app=self.app;panel=app.agent_panel
        self.assertIsInstance(app.source_contact_entry,SearchEntry)
        app.show_page('帮助');self.root.update();self.assertIsInstance(app.help_reader.entry,SearchEntry)
        app.help_reader.query.set('Ctrl+L');self.root.update();self.assertEqual(len(app.help_reader.visible),1)
        panel.scope_button.invoke();self.root.update();self.assertIsInstance(panel.scope_popup.search_entry,SearchEntry);panel.scope_popup.destroy()
        panel.show_history();self.root.update();self.assertIsInstance(panel.history_popup.search_entry,SearchEntry);panel.history_popup.destroy()
        self.assertEqual(self.errors,[])

    def test_selection_repaints_only_changed_cards_and_refreshes_new_content(self):
        self.show();view=self.app.contact_tree
        rows=[{'id':i+1,'nickname':'自建联系人 '+str(i+1),'message_count':3,'last_message':'旧摘要','last_time':'2026-10-15T00:00:00Z'} for i in range(252)]
        view.set_rows(rows,1);self.root.update()
        with patch.object(view,'paint',wraps=view.paint) as paint:
            view.selection_set('252');self.assertEqual(paint.call_count,2)
            self.assertEqual(view.cards['252'][0].fill,SELECTED);self.assertEqual(view.cards['1'][0].fill,PAPER)
            view.selection_set('252');self.assertEqual(paint.call_count,2)
        view.resize(SimpleNamespace(width=view.canvas.winfo_width()))
        with patch.object(view,'update_labels',wraps=view.update_labels) as labels:
            view.resize(SimpleNamespace(width=view.canvas.winfo_width()));self.assertEqual(labels.call_count,0)
        rows=[dict(x) for x in rows];rows[0]['last_message']='新摘要';view.set_rows(rows,252)
        self.assertEqual(view.cards['1'][2].cget('text'),'');self.assertFalse(view.cards['1'][2].winfo_manager());self.assertEqual(self.errors,[])

    def test_wheel_attach_coalesces_and_close_preserves_other_destroy_handlers(self):
        self.show();router=self.app.theme.wheel_router;self.root.update_idletasks();frame=ttk.Frame(self.root)
        router.register(frame,self.app.contact_tree.canvas,canvas=True)
        original=len(router.bindings)
        for _ in range(50):router.register(frame,self.app.contact_tree.canvas,canvas=True);router.attach_later(frame)
        self.assertEqual(len(router.bindings),original);self.assertEqual(len(router.jobs),1)
        self.root.update_idletasks();self.assertEqual(len(router.jobs),0)
        calls=[];frame.bind('<Destroy>',lambda _:calls.append(True),add='+')
        router.close();frame.destroy();self.assertEqual(calls,[True]);self.assertEqual(self.errors,[])

    def test_power_card_has_no_reset_and_remains_centered(self):
        self.show();panel=self.app.agent_panel;panel.set_catalog(CATALOG);panel.parameters_button.invoke();self.root.update()
        view=panel.power_popover
        self.assertFalse(hasattr(view,'reset'));self.assertFalse(hasattr(view,'reset_button'))
        self.assertAlmostEqual(view.title.winfo_rootx()+view.title.winfo_width()/2,view.surface.winfo_rootx()+view.surface.winfo_width()/2,delta=2)
        self.assertTrue(panel.fast_button.winfo_ismapped());self.assertTrue(panel.power_slider.winfo_ismapped())
        self.assertEqual(self.errors,[])

    def test_wheel_cleanup_uses_text_widget_path_inside_scrolled_text(self):
        from tkinter.scrolledtext import ScrolledText
        self.show();router=self.app.theme.wheel_router;area=ScrolledText(self.root)
        router.register(area,area);callback=router.bindings[str(area)][1]
        self.assertIn(callback,str(area.tk.call('bind',area._w,'<Destroy>')))
        router.close()
        self.assertNotIn(callback,str(area.tk.call('bind',area._w,'<Destroy>')))
        area.destroy();self.root.update();self.assertEqual(self.errors,[])

    def test_button_states_keep_geometry_and_disabled_actions_stay_disabled(self):
        self.show();self.app.show_page('电脑微信');self.root.update();button=self.app.detect_button;before=(button.winfo_width(),button.winfo_height());called=[]
        original=button.cget('command');button.configure(command=lambda:called.append(True))
        for state in ('active','pressed','focus'):
            button.state([state]);self.root.update_idletasks();self.assertEqual((button.winfo_width(),button.winfo_height()),before);button.state(['!'+state])
        button.state(['disabled']);button.invoke();self.assertEqual(called,[])
        button.state(['!disabled']);button.configure(command=original);self.assertEqual(self.errors,[])
