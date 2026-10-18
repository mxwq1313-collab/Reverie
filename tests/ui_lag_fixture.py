"""Synthetic mapped Tk fixtures for UI responsiveness regressions."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import time,tkinter as tk,unittest
from wechat_archive.ui.theme import Theme
from wechat_archive.ui.message_widgets import ContactList,BubbleTimeline

class NativeLagCase(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('920x640+0+0');self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args[1])
        self.theme=Theme(self.root)
        self.addCleanup(self.root.destroy);self.addCleanup(self.theme.close)
    def settle(self,predicate,timeout=5):
        start=time.monotonic()
        def poll():
            if predicate():self.root.quit();return
            if time.monotonic()-start>timeout:self.root.quit();return
            self.root.after(8,poll)
        self.root.after(8,poll);self.root.mainloop()
        self.assertTrue(predicate(),'Tk operation did not finish');self.assertEqual(self.errors,[])
    def contacts(self):
        view=ContactList(self.root,self.theme,lambda:None);view.pack(fill='both',expand=True);return view
    def timeline(self):
        view=BubbleTimeline(self.root,self.theme);view.pack(fill='both',expand=True)
        view.app=SimpleNamespace(background_browsing=True,current_page='聊天归档',message_rows=[],loaded_offset=0,message_total=1000,status=tk.StringVar(self.root),update_message_count=lambda *args:None,thumbnail_service=SimpleNamespace(submit=lambda *args:None))
        return view
    def done(self,view):
        return not any(getattr(view,name,None) for name in ('rendering','reflow_busy','layout_job','finish_job','restore_job','stack_job','layout_step_job','contact_view_job','contact_metrics_job'))
    def rows(self,n,offset=0):
        base=datetime(2025,1,1,tzinfo=timezone.utc)
        return [dict(id=i+1,sender_id=1 if i%2 else 2,sender_name='合成发送者',receiver_name='接收者',
            create_time=(base+timedelta(minutes=i)).isoformat(),content=('长段落 原文😀 '*35 if i%3==0 else '保留 空格\n与换行 ')+str(i),msg_type='text',attachments=[])
            for i in range(offset,offset+n)]
