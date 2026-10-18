"""Shared menus, indexed visible rows and exact selectable message text."""
import tkinter as tk
from types import SimpleNamespace
from unittest.mock import patch
from ui_lag_fixture import NativeLagCase

class TimelineLagTests(NativeLagCase):
    def test_one_menu_one_page_layout_and_append_preserves_old_measurement(self):
        view=self.timeline();rows=self.rows(100)
        with patch.object(view,'queue_reflow',wraps=view.queue_reflow) as reflow:
            view.set_rows_incremental(rows,1);self.settle(lambda:self.done(view))
        self.assertEqual(sum(bool(w.winfo_ismapped()) for w in view.body.winfo_children())<40,True)
        self.assertEqual(sum(isinstance(w,tk.Menu) for w in view.winfo_children()),1)
        self.assertFalse(any(isinstance(w,tk.Menu) for value in view.bubbles.values() for w in value['text'].winfo_children()))
        old=view.bubbles[1];height=old['height'];text=old['text']
        with patch.object(text,'count',wraps=text.count) as count:
            view.set_rows_incremental(self.rows(20,100),1,append=True);self.settle(lambda:self.done(view))
        self.assertIs(view.bubbles[1],old);self.assertEqual(old['height'],height);self.assertEqual(count.call_count,0)
        self.assertEqual(len(view.rows),120)
        self.assertEqual(sum(1 for call in reflow.call_args_list if call.kwargs.get('immediate')),0)
    def test_scroll_to_last_long_unicode_message_keeps_raw_and_fits_text(self):
        view=self.timeline();rows=self.rows(100)
        view.set_rows_incremental(rows,1);self.settle(lambda:self.done(view))
        view.see_message(100);self.settle(lambda:self.done(view) and view.bubbles[100]['text'].winfo_ismapped())
        value=view.bubbles[100];text=value['text']
        self.assertEqual(text.get('1.0','end-1c'),rows[-1]['content'])
        self.assertFalse(value.get('collapsed_children'))
        self.assertIsNotNone(text.bbox('end-1c'))
        bounds=text.bbox('end-1c');self.assertLessEqual(bounds[1]+bounds[3],text.winfo_height()+2)
        for width in (580,920):
            self.root.geometry(f'{width}x640');self.settle(lambda:self.done(view))
            self.assertEqual(text.get('1.0','end-1c'),rows[-1]['content'])

    def test_append_during_first_layout_is_queued_without_losing_messages(self):
        view=self.timeline();original=view.queue_reflow;queued=[]
        def queue(*args,**kwargs):
            if getattr(view,'_render_complete_pending',False) and not queued:
                queued.append(True);view.set_rows_incremental(self.rows(10,30),1,append=True)
            return original(*args,**kwargs)
        with patch.object(view,'queue_reflow',side_effect=queue):
            view.set_rows_incremental(self.rows(30),1);self.settle(lambda:self.done(view))
        self.assertEqual([row['id'] for row in view.rows],list(range(1,41)))
        self.assertEqual(len(view.bubbles),40)

    def test_switch_during_incremental_creation_unmaps_retired_content(self):
        view=self.timeline();view.set_rows_incremental(self.rows(100),1)
        self.root.after(1,lambda:view.set_rows_incremental(self.rows(8,1000),1))
        self.settle(lambda:self.done(view) and not getattr(view,'cleanup_job',None))
        self.assertEqual([row['id'] for row in view.rows],list(range(1001,1009)))
        self.assertTrue(all(value['row']['id']>=1001 for value in view.bubbles.values()))
    def test_first_layout_does_not_treat_empty_scroll_range_as_bottom_reader(self):
        view=self.timeline();original=view.queue_reflow;captured=[]
        def queue(*args,**kwargs):
            if getattr(view,'_render_complete_pending',False) and not captured:
                captured.append(True);view.remember_scroll_anchor()
            return original(*args,**kwargs)
        with patch.object(view,'queue_reflow',side_effect=queue):
            view.set_rows_incremental(self.rows(80),1);self.settle(lambda:self.done(view))
        self.assertTrue(captured);self.assertLessEqual(abs(view.canvas.canvasy(0)),1)
    def test_switch_from_sync_to_incremental_migrates_all_existing_rows(self):
        for append in (False,True):
            with self.subTest(append=append):
                view=self.timeline();view.app.background_browsing=False
                rows=self.rows(20);view.set_rows(rows,1);self.root.update()
                view.app.background_browsing=True
                view.set_rows_incremental(self.rows(5,20) if append else rows,1,append=append)
                self.settle(lambda:self.done(view) and not getattr(view,'cleanup_job',None))
                self.assertEqual(len(view.rows),25 if append else 20)
                self.assertEqual({key for _,key in view._stack_widgets if key is not None},set(view.bubbles))
                self.assertEqual(view.body.pack_slaves(),[])
                view.see_message(1);self.settle(lambda:self.done(view) and view.bubbles[1]['text'].winfo_ismapped())
                view.destroy()
    def test_long_document_tail_stays_inside_a_small_native_viewport(self):
        view=self.timeline();rows=self.rows(180)
        for row in rows:row['content']='很长的合成消息 保留中文与空格 '*80
        view.set_rows_incremental(rows,1);self.settle(lambda:self.done(view))
        self.assertGreater(view._stack_total,32767)
        view.see_message(180);self.settle(lambda:self.done(view) and view.bubbles[180]['text'].winfo_ismapped())
        self.assertGreater(view.canvas.canvasy(0),32767)
        self.assertLess(view.body.winfo_height(),self.root.winfo_height()*4)
        text=view.bubbles[180]['text'];self.assertEqual(text.get('1.0','end-1c'),rows[-1]['content'])
        self.assertIsNotNone(text.bbox('end-1c'))
        end=text.bbox('end-1c');self.assertLessEqual(text.winfo_rooty()+end[1]+end[3],view.canvas.winfo_rooty()+view.canvas.winfo_height()+3)
    def test_unseen_row_estimates_do_not_grow_after_repeated_width_changes(self):
        view=self.timeline();view.set_rows_incremental(self.rows(100),1);self.settle(lambda:self.done(view))
        value=view.bubbles[100];self.assertNotIn('measured_text_height',value)
        view.measure_cache.clear();line=self.theme.font.metrics('linespace')+self.theme.u(4)
        view.estimate_collapsed(value,450,line);expected=value['height']
        for _ in range(12):
            view.estimate_collapsed(value,600,line);view.estimate_collapsed(value,450,line)
        self.assertEqual(value['height'],expected)
    def test_first_dark_scroll_realizes_palette_and_own_marker_for_unseen_short_row(self):
        self.theme.update(self.theme.text_size,self.theme.family,'dark','zh_CN',48)
        view=self.timeline();self.theme.apply_tree(view)
        view.set_rows_incremental(self.rows(100),1);self.settle(lambda:self.done(view))
        view.see_message(98);self.settle(lambda:self.done(view) and view.bubbles[98]['text'].winfo_ismapped())
        value=view.bubbles[98]
        self.assertEqual(value['text'].cget('foreground'),self.theme.palette['INK'])
        self.assertEqual(value['outer'].cget('background'),self.theme.palette['CANVAS'])
        self.assertTrue(value['bubble'].find_withtag('shape'))
    def test_shared_menu_drops_previous_conversation_target_when_rows_clear(self):
        view=self.timeline();rows=self.rows(3);view.set_rows_incremental(rows,1);self.settle(lambda:self.done(view))
        old=view.bubbles[1]['text']
        with patch.object(view.context_menu,'tk_popup'):
            view.popup_context(SimpleNamespace(x_root=0,y_root=0),old,rows[0]['content'])
        view.clear()
        with patch.object(view,'copy_raw') as copy:
            view.context_menu.invoke(0);view.context_menu.invoke(1)
        copy.assert_not_called();self.assertIsNone(view._menu_target)
