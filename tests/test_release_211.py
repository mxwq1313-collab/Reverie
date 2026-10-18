"""2.1.1 UI contracts on synthetic records and a real native Text renderer."""
import hashlib,time,tkinter as tk,json,unittest
from pathlib import Path
from PIL import Image
import test_workbench as fixture
from wechat_archive.message_content import forwarded_document,forwarded_records,forwarded_text


def forward_xml(total=10,long=False):
    items=''.join(f'<dataitem datatype="1"><sourcename>自建伙伴{i%2}</sourcename><sourcetime>2026-10-16 10:00:{i%60:02d}</sourcetime><datadesc>消息{i} '+('这是可换行的普通原文。'*40 if long else '原文[流泪]')+'</datadesc></dataitem>' for i in range(total))
    return '<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist>'+items+'</datalist></recordinfo>]]></recorditem></appmsg></msg>'


class ForwardProjectionTests(unittest.TestCase):
    def test_top_level_total_and_preview_budget(self):
        xml=forward_xml(125);document=forwarded_document(xml)
        self.assertEqual(document['total'],125);self.assertEqual(len(document['items']),100)
        self.assertIn('125 条',forwarded_text(xml));self.assertIn('另有 117 条',forwarded_text(xml))
    def test_nested_forward_is_not_flattened_or_double_counted(self):
        nested='<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist><dataitem datatype="17"><recordinfo><datalist><dataitem datatype="1"><datadesc>内部</datadesc></dataitem></datalist></recordinfo></dataitem></datalist></recordinfo>]]></recorditem></appmsg></msg>'
        self.assertEqual(forwarded_document(nested)['total'],1);self.assertEqual(len(forwarded_records(nested)),1)
    def test_unknown_structure_entity_and_oversized_payload_are_refused(self):
        self.assertIsNone(forwarded_document('<!DOCTYPE msg [<!ENTITY x "bad">]><msg/>'))
        self.assertIsNone(forwarded_document(forward_xml().replace('<recordinfo>','<unknown>').replace('</recordinfo>','</unknown>')))
        self.assertIsNone(forwarded_document('x'*(2*1024*1024+1)))
    def test_long_record_preview_explicitly_retains_original(self):
        xml=forward_xml(1).replace('原文[流泪]','原文'*1500)
        record=forwarded_records(xml)[0];self.assertIn('完整文字保留在原文中',record['text']);self.assertIn('原文'*1500,xml)


class Release211UITests(unittest.TestCase):
    setUp=fixture.WorkbenchTests.setUp
    show=fixture.WorkbenchTests.show
    def settle(self,condition=lambda:True,seconds=6):
        stop=time.monotonic()+seconds
        while time.monotonic()<stop:
            self.root.update()
            if condition():return
            time.sleep(.005)
        self.fail('Native layout did not settle')
    def forward(self,total=10,long=False):
        self.show();row={**self.app.message_rows[0],'id':9000,'msg_type':'system','content':forward_xml(total,long),'attachments':[]}
        self.app.message_rows=[row];self.app.chat_text.set_rows([row],self.app.owner_id);self.root.update()
        return row,self.app.chat_text.bubbles[row['id']]['forward']
    def test_forward_starts_collapsed_and_raw_xml_is_unchanged(self):
        before=self.path.read_bytes();row,control=self.forward()
        self.assertFalse(control.expanded);self.assertEqual(control.rendered,[]);self.assertFalse(control.body.winfo_ismapped())
        self.assertIn('10 条',control.heading.cget('text'));self.assertLess(len(control.preview.cget('text')),200)
        self.assertNotIn('<recordinfo>',control.preview.cget('text'));self.assertEqual(self.app.chat_text.get(),row['content']);self.assertEqual(before,self.path.read_bytes())
    def test_expand_has_normal_selectable_messages_and_inline_emoticons(self):
        row,control=self.forward();control.heading.invoke();self.settle(lambda:len(control.rendered)==10 and not control.resize_job)
        text=control.rendered[0][2];self.assertEqual(text.get('1.0','end-1c'),'消息0 原文[流泪]');self.assertEqual(len(text.image_names()),1)
        text.tag_add('sel','1.0','1.3');self.app.chat_text.copy_selection(text);self.assertEqual(self.root.clipboard_get(),'消息0')
        control.menu.invoke(1);self.assertEqual(self.root.clipboard_get(),row['content']);self.assertEqual(self.errors,[])

    def test_paged_expand_collapse_and_reopen_cancel_pending_jobs(self):
        _,control=self.forward(125);control.toggle();self.settle(lambda:len(control.rendered)==20 and not control.resize_job)
        self.assertIn('20 / 125',control.count.cget('text'))
        for _ in range(5):control.more_records()
        self.settle(lambda:len(control.rendered)==100 and not control.resize_job)
        self.assertEqual(len({item['text'] for item in control.records[:len(control.rendered)]}),100)
        self.assertIn('最多预览100条',control.count.cget('text'));control.collapse();self.root.update()
        self.assertEqual(control.rendered,[]);self.assertIsNone(control.render_job);self.assertFalse(control.expanded)
        control.toggle();control.collapse();self.root.after(80,self.root.quit);self.root.mainloop();self.assertEqual(self.errors,[])
    def test_scope_replacement_destroys_expanding_forward_safely(self):
        _,control=self.forward(80);control.toggle();self.app.chat_text.clear();self.root.after(100,self.root.quit);self.root.mainloop();self.assertFalse(control.winfo_exists());self.assertEqual(self.errors,[])
    def test_long_forward_wraps_after_width_changes(self):
        _,control=self.forward(3,True);control.toggle();self.settle(lambda:len(control.rendered)==3 and not control.resize_job)
        self.root.geometry('900x700');self.settle(lambda:not control.resize_job)
        widget=control.rendered[0][2];self.root.update();last=widget.bbox('end-1c');self.assertIsNotNone(last);self.assertLessEqual(last[1]+last[3],widget.winfo_height()+2)
        self.assertEqual(self.errors,[])
    def test_multiline_forward_includes_the_final_paragraph_without_inner_scrolling(self):
        self.show();body='\n'.join('段落'+str(index) for index in range(16))+'\n尾行[流泪]'
        row={**self.app.message_rows[0],'id':9001,'msg_type':'system','content':forward_xml(1).replace('消息0 原文[流泪]',body),'attachments':[]}
        self.app.chat_text.set_rows([row],self.app.owner_id);self.root.update();control=self.app.chat_text.bubbles[9001]['forward']
        control.toggle();self.settle(lambda:len(control.rendered)==1 and not control.resize_job);widget=control.rendered[0][2];self.root.update()
        self.assertEqual(widget.get('1.0','end-1c'),body);last=widget.bbox('end-1c');self.assertIsNotNone(last)
        self.assertLessEqual(last[1]+last[3],widget.winfo_height()+2);self.assertEqual(widget.yview(),(0.0,1.0))

    def test_multiple_long_forwards_realize_only_visible_messages_and_reveal_on_scroll(self):
        self.show();app=self.app;app.background_browsing=True;base=app.message_rows[0]
        rows=[{**base,'id':9100+index,'content':forward_xml(10,True),'msg_type':'system','attachments':[]} for index in range(3)]
        app.chat_text.set_rows(rows,app.owner_id);self.root.update();controls=[value['forward'] for value in app.chat_text.bubbles.values()]
        for control in controls:control.toggle()
        self.settle(lambda:all(len(c.rendered)==10 and not c.resize_job and not c.render_job for c in controls))
        shown=sum(text.winfo_ismapped() for c in controls for _,_,text in c.rendered if text is not None)
        visible_state={'top':app.chat_text.canvas.canvasy(0),'region':app.chat_text.canvas.cget('scrollregion'),
                       'body':(app.chat_text.body.winfo_y(),app.chat_text.body.winfo_height(),app.chat_text.body.winfo_width()),
                       'window':getattr(app.chat_text,'_stack_window_geometry',None),
                       'controls':[(c.timeline_y(),c.master.winfo_y(),c.master.winfo_height(),c.master.winfo_reqheight(),c.winfo_y(),c.winfo_height(),c.winfo_width(),c.body.winfo_y(),c.body.winfo_width(),c.winfo_viewable(),c.needs_fit,c.resize_job,[(f.winfo_y(),f.winfo_height(),f.winfo_width(),f._forward_virtual,t is not None) for f,_,t in c.rendered]) for c in controls]}
        self.assertGreater(shown,0,repr(visible_state));self.assertLess(shown,12)
        app.chat_text.canvas.yview_moveto(1);self.root.update();app.chat_text.refresh_visible()
        try:
            self.settle(lambda:controls[-1].rendered[-1][2] is not None and controls[-1].rendered[-1][2].winfo_ismapped() and not controls[-1].resize_job)
        except AssertionError:
            view=app.chat_text;control=controls[-1]
            state={'window':(self.root.winfo_width(),self.root.winfo_height()),'scale':app.theme.scale,
                   'canvas_top':view.canvas.canvasy(0),'region':view.canvas.cget('scrollregion'),
                   'stack_total':getattr(view,'_stack_total',None),'stack_window':getattr(view,'_stack_window_geometry',None),
                   'logical_y':control.timeline_y(),'outer':(control.master.winfo_y(),control.master.winfo_rooty(),control.master.winfo_height(),control.master.winfo_reqheight()),
                   'control':(control.winfo_y(),control.winfo_rooty(),control.winfo_height(),control.winfo_reqheight(),control.winfo_viewable()),
                   'body':(control.body.winfo_y(),control.body.winfo_height(),control.body.winfo_reqheight()),
                   'frames':[(frame.winfo_y(),frame.winfo_rooty(),frame.winfo_height(),frame.winfo_reqheight(),frame._forward_virtual,text is not None,text.winfo_ismapped() if text is not None else False) for frame,_,text in control.rendered]}
            self.fail('Forward layout: '+repr(state))
        last=controls[-1].rendered[-1][2];self.assertIn('消息9',last.get('1.0','end-1c'));self.assertEqual(last.yview(),(0.0,1.0))
        self.assertEqual(self.errors,[])

    def test_capsule_bottom_entry_is_above_statistics_and_outside_tools(self):
        self.show();app=self.app;app.capsule_button.invoke();self.root.update()
        self.assertEqual(app.current_page,'时光胶囊');self.assertTrue(app.toolbox_panel.capsule.memory.winfo_ismapped())
        self.assertNotIn('时光胶囊',app.tab_routes);self.assertLess(app.capsule_button.winfo_y(),app.nav_note.winfo_y())
        self.assertNotEqual(app.capsule_button.icon,app.nav_note.icon);self.assertIsNone(app.agent_panel.client)
    def test_workshop_is_tool_tab_and_random_memory_is_a_small_utility(self):
        self.show();app=self.app;app.show_page('随机回忆');self.root.update()
        self.assertIn('随机回忆',app.tab_routes);self.assertTrue(app.toolbox_panel.random.memory.winfo_ismapped())
        for name in ('随机回忆',):
            app.show_page(name);self.root.update();self.assertEqual(app.current_page,'工具与设置')
            notebook,tab=app.tab_routes[name];self.assertIs(notebook,app.tools_notebook);self.assertEqual(notebook.select(),str(tab));self.assertTrue(app.toolbox_panel.views[name].winfo_ismapped())
    def test_all_peer_tabs_remain_reachable_with_large_text_and_narrow_window(self):
        self.show(900,700);app=self.app;app.show_page('随机回忆');app.theme.update(24,app.theme.family,app.theme.mode,'zh_CN',48);app.adapt_layout();self.root.update();app.fit_tool_tabs();self.root.update()
        found=set();notebook=app.tools_notebook
        for x in range(1,notebook.winfo_width(),3):
            try:found.add(notebook.index(f'@{x},{app.theme.u(15)}'))
            except tk.TclError:pass
        self.assertEqual(found,set(range(3)));self.assertEqual(self.errors,[])
    def test_real_avatar_pixels_are_rounded_square_and_placeholder_is_consistent(self):
        image=self.folder/'avatar.png';Image.new('RGB',(64,64),'#d87e77').save(image);self.service.update_user(2,avatar=str(image));self.app.load_contacts()
        card=self.app.contact_tree.cards['2'][0];canvas=next(w for w in card.content.winfo_children() if isinstance(w,tk.Canvas));self.settle(lambda:canvas.avatar_available);photo=str(canvas.avatar_image);u=self.app.theme.u
        self.assertFalse(self.root.tk.call(photo,'transparency','get',u(4),u(4)));self.assertTrue(self.root.tk.call(photo,'transparency','get',0,0))
        other=self.app.contact_tree.cards['3'][0];fallback=next(w for w in other.content.winfo_children() if isinstance(w,tk.Canvas));self.assertTrue(any(fallback.type(item)=='polygon' for item in fallback.find_all()))
    def test_version_and_replacement_logo_asset(self):
        from wechat_archive import __version__
        from wechat_archive.ui.app_logo import original
        self.assertEqual(__version__,'2.2.4');metadata=json.loads((Path(__file__).resolve().parents[1]/'wechat_archive/ui/assets/app_logo.json').read_text(encoding='utf-8'))
        self.assertEqual(metadata['name'],'思绪缠结的可爱猫咪');self.assertEqual(hashlib.sha256(original()).hexdigest(),metadata['sha256'])


if __name__=='__main__':unittest.main(verbosity=2)
