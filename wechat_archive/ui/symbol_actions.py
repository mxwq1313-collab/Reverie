"""Icon actions retain accessible names and explain themselves on hover/focus."""
import tkinter as tk
from tkinter import ttk

def action_icon(text):
    return {'日期':'calendar','date':'calendar'}.get(str(text).strip().lower())


class HoverHint:
    def __init__(self,widget,theme):
        self.widget=widget;self.theme=theme;self.job=None;self.tip=None
        for event in ('<Enter>','<FocusIn>'):widget.bind(event,self.schedule,add='+')
        for event in ('<Leave>','<FocusOut>','<Button-1>','<Destroy>'):widget.bind(event,self.hide,add='+')
    def schedule(self,event=None):
        self.hide();self.job=self.widget.after(300,self.show)
    def show(self):
        self.job=None;w=self.widget
        if not w.winfo_ismapped():return
        text=getattr(w,'symbol_hint',None) or str(w.cget('text'))
        if callable(text):text=text()
        extra=getattr(w,'tooltip_extra','')
        if extra:text+='\n'+(extra() if callable(extra) else extra)
        self.tip=tk.Toplevel(w);self.tip.overrideredirect(True);self.tip.attributes('-topmost',True)
        from .rounded import RoundedSurface
        surface=RoundedSurface(self.tip,self.theme,self.theme.palette['PAPER'],self.theme.palette['HOVER'],outline=self.theme.palette['LINE'],radius=8,padding=8);surface.pack()
        label=tk.Label(surface.content,text=text,background=self.theme.palette['HOVER'],foreground=self.theme.palette['INK'],font=self.theme.small,padx=3,pady=1,justify='left',wraplength=self.theme.u(320));label.pack()
        label.update_idletasks();surface.configure(width=label.winfo_reqwidth()+surface.padding*2)
        self.tip.update_idletasks();x=max(0,min(w.winfo_rootx(),w.winfo_screenwidth()-self.tip.winfo_reqwidth()-8));y=min(w.winfo_rooty()+w.winfo_height()+5,w.winfo_screenheight()-self.tip.winfo_reqheight()-8)
        self.tip.geometry(f'+{x}+{max(0,y)}')
    def hide(self,event=None):
        if self.job:
            try:self.widget.after_cancel(self.job)
            except tk.TclError:pass
            self.job=None
        if self.tip:
            try:self.tip.destroy()
            except tk.TclError:pass
            self.tip=None


def symbolize(button,theme):
    if button.winfo_class() not in ('TButton','TCheckbutton') or hasattr(button,'icon') or getattr(button,'_keep_caption',False):return
    if str(button.cget('textvariable')):return
    if (getattr(button,'_symbol_only',False) or getattr(button,'symbol_hint',None)) and not hasattr(button,'_action_hint'):button._action_hint=HoverHint(button,theme)
    if not getattr(button,'_symbol_only',False) or hasattr(button,'_symbol_key'):return
    icon=action_icon(button.cget('text'))
    if not icon:return
    from .icon_button import icon_image
    original=button.configure;original_state=button.state;button._symbol_key=None
    def refresh():
        if not button.winfo_exists():return
        text=str(button.cget('text'));name=action_icon(text) or icon
        color=theme.palette['MUTED' if button.instate(['disabled']) else 'ACCENT' if 'Selected' in str(button.cget('style')) else 'INK'];key=(name,color,theme.u(20),theme.control_height)
        if key==button._symbol_key:return
        button._symbol_key=key;cache=getattr(theme,'icon_cache',None)
        if cache is None:theme.icon_cache=cache={}
        image_key=key[:3]
        if image_key not in cache:cache[image_key]=icon_image(theme.root,*image_key)
        original(image=cache[image_key],compound='image',width=0,padding=(theme.u(6),max(1,(theme.control_height-theme.u(20))//2)))
    def configure(cnf=None,**kwargs):
        result=original(cnf,**kwargs)
        if kwargs or isinstance(cnf,dict):refresh()
        return result
    def state(spec=None):
        result=original_state(spec)
        if spec is not None:refresh()
        return result
    button.configure=button.config=configure;button.state=state;button.refresh_icon=refresh;refresh()
