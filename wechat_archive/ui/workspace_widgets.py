"""Shared quiet cards and wrapping action rows for native desktop pages."""
import tkinter as tk
from tkinter import ttk


def card(parent,theme,title,hint=''):
    u=theme.u
    frame=ttk.Frame(parent,style='Card.TFrame',padding=u(18));frame.pack(fill='x',pady=(0,u(14)))
    ttk.Label(frame,text=title,font=theme.name).pack(anchor='w',pady=(0,u(5)))
    if hint:
        label=ttk.Label(frame,text=hint,style='Hint.TLabel',wraplength=u(680));label.pack(fill='x',pady=(0,u(12)))
    def fit(event):
        if event.widget is not frame:return
        width=max(u(100),event.width-u(36))
        if getattr(frame,'_wrap_width',None)==width:return
        frame._wrap_width=width
        for child in frame.winfo_children():
            if child.winfo_class() in ('Label','TLabel') and child.winfo_pixels(child.cget('wraplength') or 0)>0:child.configure(wraplength=width)
    frame.bind('<Configure>',fit,add='+')
    return frame


class ActionRow(ttk.Frame):
    def __init__(self,parent,theme):
        super().__init__(parent);self.theme=theme;self.items=[];self.job=None;self.last=None;self.closed=False
        self.pack(fill='x',pady=theme.u(5));self.bind('<Configure>',self.schedule);self.bind('<Destroy>',self.close,add='+')
    def add(self,widget):
        self.items.append(widget);widget.bind('<Configure>',lambda _:self.schedule(),add='+');widget.grid(row=0,column=len(self.items)-1,sticky='w',padx=(0,self.theme.u(7)),pady=self.theme.u(3));self.schedule();return widget
    def schedule(self,event=None):
        if self.closed:return
        if event is not None and event.widget is not self:return
        if self.job:self.after_cancel(self.job)
        self.job=self.after_idle(self.layout)
    def layout(self):
        self.job=None;width=max(1,self.winfo_width());row=column=used=0
        signature=(width,tuple(w.winfo_reqwidth() for w in self.items))
        if signature==self.last:return
        self.last=signature
        for widget in self.items:
            requested=widget.winfo_reqwidth()+self.theme.u(7)
            if used and used+requested>width:row+=1;column=used=0
            widget.grid_configure(row=row,column=column);column+=1;used+=requested
    def close(self,event=None):
        if event is None or event.widget is self:
            self.closed=True
            if self.job:self.after_cancel(self.job);self.job=None


def polish_dialog(window,app):
    if getattr(window,'_sixu_dialog',False) or window.overrideredirect():return
    window._sixu_dialog=True;window.configure(background=app.theme.palette['CANVAS'])
    previous=window.minsize()
    window.minsize(max(previous[0],min(window.winfo_width(),app.theme.u(420))),max(previous[1],min(window.winfo_height(),app.theme.u(280))))
    if not window.bind('<Escape>'):window.bind('<Escape>',lambda _:window.destroy())
    app.theme.apply_tree(window);app.localizer.apply(window,())
