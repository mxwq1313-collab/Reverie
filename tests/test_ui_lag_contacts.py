"""Contact reuse, debounced labels, background avatars and member layout."""
from pathlib import Path
from types import SimpleNamespace
import tempfile,threading,time,tkinter as tk
from unittest.mock import patch
from PIL import Image
from ui_lag_fixture import NativeLagCase

class ContactLagTests(NativeLagCase):
    def test_contacts_reuse_kept_rows_and_keyboard_reaches_last(self):
        view=self.contacts();rows=[dict(id=i,nickname=f'合成联系人{i}',message_count=i+1) for i in range(200)]
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        old=view.cards['50'][0];view.set_rows_incremental(rows[50:100],50);self.settle(lambda:self.done(view))
        self.assertIs(view.cards['50'][0],old);self.assertEqual(len(view.rows),50)
        view.move_selected(1000);self.settle(lambda:view.cards['99'][0].winfo_ismapped())
        self.assertEqual(view.selection(),('99',));self.assertLess(len(view._mapped_cards),35)
        self.assertTrue(view.cards['99'][0].winfo_ismapped())
    def test_contact_resize_coalesces_measurement_and_keeps_final_name(self):
        view=self.contacts();rows=[dict(id=i,nickname='很长的合成姓名'*8+str(i),message_count=2) for i in range(80)]
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        with patch.object(view,'update_labels',wraps=view.update_labels) as labels:
            for width in range(260,410,10):view.resize(SimpleNamespace(width=width))
            self.assertEqual(labels.call_count,0)
            self.settle(lambda:not view.label_job)
            self.assertGreater(labels.call_count,0);self.assertLess(labels.call_count,35)
        width=400
        expected=self.theme.elide(rows[0]['nickname'],max(self.theme.u(40),width-self.theme.u(113)))
        self.assertEqual(view.cards['0'][1].cget('text'),expected)
    def test_async_avatar_worker_yields_and_invalid_image_keeps_placeholder(self):
        view=self.contacts();entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        original=view.avatar_service.decode
        def slow(key):entered.set();release.wait(2);return original(key)
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'avatar.png';bad=Path(folder)/'bad.png'
            Image.new('RGB',(256,256),'#559977').save(image);bad.write_bytes(b'invalid')
            with patch.object(view.avatar_service,'decode',side_effect=slow):
                view.set_rows_incremental([dict(id=1,nickname='合成头像',message_count=1,avatar=str(image)),dict(id=2,nickname='损坏头像',message_count=1,avatar=str(bad))],1)
                self.settle(entered.is_set)
                ticks=[];self.root.after(1,lambda:ticks.append(True));self.settle(lambda:bool(ticks))
                view.move_selected(1);self.assertEqual(view.selection(),('2',));release.set()
                canvas=next(w for w in view.cards['1'][0].content.winfo_children() if isinstance(w,tk.Canvas))
                self.settle(lambda:canvas.avatar_available)
                self.settle(lambda:not view.avatar_service.active and not view.avatar_service.pending)
                self.assertFalse(next(w for w in view.cards['2'][0].content.winfo_children() if isinstance(w,tk.Canvas)).avatar_available)
                self.assertLessEqual(len(view.avatar_service.cache),256)
    def test_virtual_group_members_expand_without_losing_other_contacts(self):
        view=self.contacts();members=[dict(nickname='成员'+str(i),message_count=2,ratio=.5) for i in range(8)]
        rows=[dict(id=-1,nickname='自建群',message_count=16,kind='group',members=members),dict(id=2,nickname='下一行',message_count=1)]
        view.set_rows_incremental(rows,-1);self.settle(lambda:self.done(view))
        card=view.cards['-1'][0];button=next(w for w in card.content.winfo_children() if isinstance(w,tk.Button))
        button.invoke();self.settle(lambda:card.member_section.winfo_ismapped())
        self.assertGreater(view._contact_offsets[1],card.member_section.winfo_reqheight())
        button.invoke();self.settle(lambda:not card.member_section.winfo_ismapped())
        self.assertEqual(view.get_children(),('-1','2'))
    def test_avatar_clear_discards_results_from_previous_archive(self):
        view=self.contacts();entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        original=view.avatar_service.decode
        def slow(key):entered.set();release.wait(2);return original(key)
        with tempfile.TemporaryDirectory() as folder:
            image=Path(folder)/'avatar.png';Image.new('RGB',(64,64),'#337755').save(image)
            with patch.object(view.avatar_service,'decode',side_effect=slow):
                view.set_rows_incremental([dict(id=1,nickname='旧归档',message_count=1,avatar=str(image))],1)
                self.settle(entered.is_set)
                view.avatar_service.clear()
                view.set_rows_incremental([dict(id=1,nickname='新归档',message_count=1,avatar=None)],1)
                release.set();self.settle(lambda:self.done(view) and not view.avatar_service.job)
            canvas=next(w for w in view.cards['1'][0].content.winfo_children() if isinstance(w,tk.Canvas))
            self.assertFalse(canvas.avatar_available);self.assertFalse(view.avatar_service.cache)
    def test_new_rows_cancel_old_debounced_label_batches(self):
        view=self.contacts();rows=[dict(id=i,nickname='旧身份联系人'+str(i),message_count=1) for i in range(40)]
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        changed=[dict(row,nickname='新身份联系人'+str(row['id'])) for row in rows]
        state={'switched':False};stale=[];original=view.update_labels
        def slow(row,width):
            if state['switched'] and row['nickname'].startswith('旧'):stale.append(row['id'])
            time.sleep(.004);return original(row,width)
        def switch():
            state['switched']=True;view.set_rows_incremental(changed,0)
        with patch.object(view,'update_labels',side_effect=slow):
            view.resize(SimpleNamespace(width=300));self.root.after(121,switch)
            self.settle(lambda:state['switched'] and self.done(view) and not view.label_job)
        self.assertEqual(stale,[])
        for key in view._mapped_cards:
            self.assertTrue(str(view.cards[key][1].cget('text')).startswith('新身份'))
    def test_unchanged_sync_rows_migrate_to_visible_layout_without_rebuilding(self):
        view=self.contacts();rows=[dict(id=i,nickname='合成联系人'+str(i),message_count=1) for i in range(40)]
        view.set_rows(rows,0);self.root.update();kept=view.cards['0'][0]
        self.assertFalse(getattr(view,'virtualized',False))
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        self.assertTrue(view.virtualized);self.assertIs(view.cards['0'][0],kept)
        self.assertEqual(len(view.rows),40);self.assertEqual(view.body.pack_slaves(),[])
        self.assertLess(sum(parts[0].winfo_ismapped() for parts in view.cards.values()),35)
    def test_large_contact_document_uses_a_small_native_viewport(self):
        view=self.contacts();rows=[dict(id=i,nickname='合成联系人'+str(i),message_count=1) for i in range(700)]
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        self.assertGreater(view._contact_offsets[-1],32767)
        view.move_selected(100000);self.settle(lambda:view.cards['699'][0].winfo_ismapped())
        self.assertGreater(view.canvas.canvasy(0),32767)
        self.assertLess(view.body.winfo_height(),self.root.winfo_height()*4)
        card=view.cards['699'][0]
        self.assertLess(card.winfo_rooty(),view.canvas.winfo_rooty()+view.canvas.winfo_height())
    def test_contact_extent_ignores_unfitted_canvas_default_height(self):
        view=self.contacts();rows=[dict(id=i,nickname='合成联系人'+str(i),message_count=1) for i in range(60)]
        view.set_rows_incremental(rows,0);self.settle(lambda:self.done(view))
        for key,parts in view.cards.items():
            if key not in view._mapped_cards:parts[0].configure(height=278)
        view.layout_contact_offsets()
        self.assertLess(view._contact_offsets[-1],len(rows)*self.theme.u(120))
        view.move_selected(10000);self.settle(lambda:view.cards['59'][0].winfo_ismapped())
        self.assertLess(view.cards['59'][0].winfo_height(),self.theme.u(120))
