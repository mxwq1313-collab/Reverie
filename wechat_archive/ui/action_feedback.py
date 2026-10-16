"""Native press feedback plus a nonmodal, truthful operation receipt."""
import tkinter as tk
from tkinter import ttk


class ActionFeedback:
    def __init__(self,app):
        self.app=app;self.root=app.root;self.closed=False;self.job=None;self.before='';self.tag='SixuActions'+str(id(self))
        self.frame=tk.Frame(app.root,background=app.theme.palette['ACCENT'],padx=1,pady=1)
        self.label=tk.Label(self.frame,background=app.theme.palette['PAPER'],foreground=app.theme.palette['INK'],font=app.theme.small,padx=14,pady=9,justify='left',wraplength=app.theme.u(420))
        self.label.pack(fill='both',expand=True);self.message='';self.tone='info';self.receipt_jobs=set()
        for event,callback in (('<ButtonPress-1>',self.press),('<ButtonRelease-1>',self.release),('<KeyPress-space>',self.press),('<KeyRelease-space>',self.release),('<KeyPress-Return>',self.press),('<KeyRelease-Return>',self.release)):
            self.root.bind_class(self.tag,event,callback)
    def attach(self,widget):
        tags=widget.bindtags()
        if self.tag in tags:return
        index=tags.index('TButton') if 'TButton' in tags else 1
        widget.bindtags((*tags[:index],self.tag,*tags[index:]))
    def press(self,event):self.before=self.app.status.get()
    def release(self,event):
        if self.closed or not event.widget.winfo_exists():return
        widget=event.widget
        if widget.instate(['disabled']):return
        if getattr(event,'keysym','??')=='??' and not (0<=event.x<widget.winfo_width() and 0<=event.y<widget.winfo_height()):return
        label=str(widget.cget('text'));variable=str(widget.cget('textvariable'))
        if variable:
            try:label=str(widget.getvar(variable))
            except tk.TclError:pass
        before=self.before
        def received():
            self.receipt_jobs.discard(job);self.receipt(label,before)
        job=self.root.after_idle(received);self.receipt_jobs.add(job)
    def receipt(self,label,before):
        if self.closed:return
        if label in ('聊天归档','添加记录','导出归档','工具','工具与设置','设置','帮助','聊天','添加','导出','归档管理','语义检索','随机回忆','文字小工坊','时光胶囊'):
            self.hide();return
        status=self.app.status.get()
        if status!=before and status:self.show(status)
    def show(self,message,tone=None):
        if self.closed:return
        if message.startswith('正在检测电脑微信账号'):
            self.hide();return
        if self.job:self.root.after_cancel(self.job)
        self.message=message[:180];self.tone=tone or ('attention' if any(x in message for x in ('失败','未完成','请选择','未保存','未复制','没有')) else 'info')
        p=self.app.theme.palette
        self.frame.configure(background=p['DANGER'] if self.tone=='attention' else p['ACCENT'])
        self.label.configure(text=self.message,background=p['PAPER'],foreground=p['INK'],font=self.app.theme.small,wraplength=max(160,min(self.app.theme.u(420),self.app.page_host.winfo_width()-40)))
        self.frame.place(relx=0,rely=1,anchor='sw',x=self.app.nav.winfo_width()+self.app.theme.u(18),y=-self.app.theme.u(45));self.frame.lift()
        self.job=self.root.after(2400,self.hide)
    def hide(self):
        if self.job:self.root.after_cancel(self.job)
        self.job=None;self.frame.place_forget()
    def close(self):
        self.closed=True
        for job in self.receipt_jobs:self.root.after_cancel(job)
        self.receipt_jobs.clear()
        if self.job:self.root.after_cancel(self.job)
        for event in ('<ButtonPress-1>','<ButtonRelease-1>','<KeyPress-space>','<KeyRelease-space>','<KeyPress-Return>','<KeyRelease-Return>'):self.root.unbind_class(self.tag,event)
