"""Actual Tk wheel events on synthetic content, including nested controls."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import unittest

from wechat_archive.ui.theme import Theme
from wechat_archive.ui.common_widgets import ScrollPanel, Collapsible
from wechat_archive.ui.message_widgets import BubbleTimeline, ContactList


class WheelTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('500x360+0+0')
        self.theme=Theme(self.root);self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args)
        self.addCleanup(self.root.destroy)

    def event(self, widget, delta=-120):
        widget.event_generate('<MouseWheel>',delta=delta)
        self.root.update()
        self.assertEqual(self.errors,[])

    def panel(self):
        panel=ScrollPanel(self.root,self.theme);panel.pack(fill='both',expand=True)
        self.labels=[]
        for i in range(50):
            label=ttk.Label(panel.body,text=f'Synthetic settings {i}');label.pack(pady=8)
            self.labels.append(label)
        self.root.update();return panel

    def test_wheel_over_child_label_scrolls_settings_by_fixed_distance(self):
        panel=self.panel();before=panel.canvas.canvasy(0)
        self.event(self.labels[0]);self.assertAlmostEqual(panel.canvas.canvasy(0)-before,self.theme.u(48),delta=2)

    def test_precision_canvas_delta_is_not_discarded(self):
        panel=self.panel();before=panel.canvas.canvasy(0)
        self.event(self.labels[0],-20);self.assertGreater(panel.canvas.canvasy(0),before)

    def test_dynamic_collapsible_descendants_receive_wheel(self):
        panel=self.panel();options=Collapsible(panel.body,'Additional options',self.theme);options.pack(fill='x')
        options.set_expanded(True);button=ttk.Button(options.content,text='Synthetic option');button.pack()
        self.root.update();panel.canvas.yview_moveto(.5);before=panel.canvas.yview()[0]
        self.event(button,120);self.assertLess(panel.canvas.yview()[0],before)

    def test_text_scrolls_locally_and_does_not_move_other_panel(self):
        panel=self.panel();text=ScrolledText(panel.body,height=3);text.pack();self.theme.text_surface(text)
        text.insert('end','\n'.join(f'line {i}' for i in range(100)));self.root.update()
        parent=panel.canvas.yview();text.yview_moveto(.1)
        self.event(text);self.assertGreater(text.yview()[0],.1);self.assertEqual(panel.canvas.yview(),parent)

    def test_nested_text_boundary_hands_wheel_to_parent(self):
        panel=self.panel();text=ScrolledText(panel.body,height=3);text.pack();self.theme.text_surface(text)
        text.insert('end','\n'.join(f'line {i}' for i in range(20)));self.root.update()
        text.yview_moveto(1);panel.canvas.yview_moveto(.4);before=panel.canvas.yview()[0]
        self.event(text);self.assertGreater(panel.canvas.yview()[0],before)

    def test_precision_text_events_accumulate_and_reverse_direction(self):
        text=ScrolledText(self.root);text.pack(fill='both',expand=True);self.theme.text_surface(text)
        text.insert('end','\n'.join(f'line {i}' for i in range(100)));self.root.update()
        text.yview_moveto(.3);self.root.update();start=text.yview()[0]
        for _ in range(4):self.event(text,-20)
        self.assertGreater(text.yview()[0],start)
        before=text.yview()[0]
        for _ in range(4):self.event(text,20)
        self.assertLess(text.yview()[0],before)

    def test_message_metadata_bubble_margin_and_text_all_scroll_timeline(self):
        timeline=BubbleTimeline(self.root,self.theme);timeline.pack(fill='both',expand=True)
        rows=[{'id':i,'sender_id':1 if i%2 else 2,'receiver_id':2 if i%2 else 1,'sender_name':'Synthetic self' if i%2 else 'Synthetic peer','receiver_name':'Peer','content':'Synthetic message '+str(i),'create_time':'2026-10-14T00:00:00Z'} for i in range(40)]
        timeline.set_rows(rows,1);self.root.update()
        item=timeline.bubbles[0]
        for widget in (timeline.body,item['label'],item['outer'],item['bubble'],item['text']):
            timeline.canvas.yview_moveto(.2);before=timeline.canvas.yview()[0]
            self.event(widget);self.assertGreater(timeline.canvas.yview()[0],before)
        item['text'].tag_add('sel','1.0','1.9');self.event(item['text'])
        self.assertEqual(item['text'].get('sel.first','sel.last'),'Synthetic')

    def test_contact_avatar_and_label_scroll_without_selection_change(self):
        contacts=ContactList(self.root,self.theme,lambda:None);contacts.pack(fill='both',expand=True)
        contacts.set_rows([{'id':i,'nickname':'Synthetic contact '+str(i),'message_count':5,'last_message':'Preview','last_time':'2026-10-14T00:00:00Z'} for i in range(30)],0)
        self.root.update();card=contacts.cards['0'][0]
        for widget in (card,card.content.winfo_children()[0],contacts.cards['0'][1]):
            contacts.canvas.yview_moveto(.2);before=contacts.canvas.yview()[0]
            self.event(widget);self.assertGreater(contacts.canvas.yview()[0],before)
            self.assertEqual(contacts.selection(),('0',))

    def test_root_and_other_panel_remain_still(self):
        panel=self.panel();before=panel.canvas.yview();self.event(self.root)
        self.assertEqual(panel.canvas.yview(),before)

    def test_destroyed_dynamic_regions_do_not_leave_handlers(self):
        panel=self.panel();panel.destroy();self.root.update()
        self.assertEqual(self.theme.wheel_router.scopes,{})
        self.event(self.root)


if __name__=='__main__':unittest.main()
