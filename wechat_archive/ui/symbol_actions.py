"""Icon actions retain accessible names and explain themselves on hover/focus."""
import tkinter as tk
from tkinter import ttk

def action_icon(text):
    return {'日期':'calendar','date':'calendar'}.get(str(text).strip().lower())


class HoverHint:
    def __init__(self,widget,theme):
        self.widget=widget;self.theme=theme;self.job=None;self.tip=None;self.layout_job=None;self.owner_binding=None;self.hovering=False
        widget.bind('<Enter>',self.enter,add='+');widget.bind('<FocusIn>',self.schedule,add='+')
        widget.bind('<Leave>',self.leave,add='+');widget.bind('<FocusOut>',self.focus_out,add='+')
        for event in ('<Button-1>','<Escape>','<Unmap>','<Destroy>'):widget.bind(event,self.hide,add='+')

    def enter(self,event=None):self.hovering=True;self.schedule(event)
    def leave(self,event=None):self.hovering=False;self.hide(event)
    def focus_out(self,event=None):
        if not self.hovering:self.hide(event)

    def schedule(self,event=None):
        if self.job or self.tip is not None:return
        self.job=self.widget.after(300,self.show)

    def show(self):
        if self.job:
            try:self.widget.after_cancel(self.job)
            except tk.TclError:pass
        self.job=None;w=self.widget
        if self.tip is not None or not w.winfo_viewable():return
        active=getattr(self.theme,'active_hover_hint',None)
        if active is not None and active is not self:active.hide()
        text=getattr(w,'symbol_hint',None) or str(w.cget('text'))
        if callable(text):text=text()
        extra=getattr(w,'tooltip_extra','')
        if extra:text+='\n'+(extra() if callable(extra) else extra)
        tip=self.tip=tk.Toplevel(w);tip.withdraw();tip.overrideredirect(True);tip.attributes('-topmost',True)
        self.theme.active_hover_hint=self
        if hasattr(w,'tip'):w.tip=tip
        outer=self.theme.palette['SIDEBAR']
        if tip.tk.call('tk','windowingsystem')=='win32':
            outer='#fe00fe';tip.configure(background=outer);tip.attributes('-transparentcolor',outer)
            self.no_activate(tip)
        from .rounded import RoundedSurface
        surface=RoundedSurface(tip,self.theme,outer,self.theme.palette['HOVER'],outline=self.theme.palette['LINE'],radius=8,padding=8);surface.pack()
        label=tk.Label(surface.content,text=text,background=self.theme.palette['HOVER'],foreground=self.theme.palette['INK'],font=self.theme.small,padx=3,pady=1,justify='left',wraplength=min(self.theme.u(320),max(80,w.winfo_screenwidth()-48)));label.pack()
        width=label.winfo_reqwidth()+surface.padding*2;height=label.winfo_reqheight()+surface.padding*2
        surface.configure(width=width,height=height)
        def place():
            self.layout_job=None
            if self.tip is not tip or not w.winfo_viewable():return
            screen_w,screen_h=w.winfo_screenwidth(),w.winfo_screenheight();gap=self.theme.u(8)
            wx,wy,ww,wh=w.winfo_rootx(),w.winfo_rooty(),w.winfo_width(),w.winfo_height()
            # Place beside the rail, never over its hover target or beyond the screen.
            x=wx+ww+gap if wx+ww+gap+width<=screen_w-gap else wx-width-gap
            y=wy+(wh-height)//2;x=max(gap,min(x,screen_w-width-gap));y=max(gap,min(y,screen_h-height-gap))
            tip.geometry(f'{width}x{height}+{x}+{y}');tip.deiconify()
        self.layout_job=w.after_idle(place)
        owner=w.winfo_toplevel()
        def changed(event):
            if event.widget is owner:self.hide()
        self.owner_binding=(owner,owner.bind('<Configure>',changed,add='+'))

    @staticmethod
    def no_activate(tip):
        import ctypes as c
        try:
            user=c.WinDLL('user32',use_last_error=True)
            user.GetParent.argtypes=[c.c_void_p];user.GetParent.restype=c.c_void_p
            get=getattr(user,'GetWindowLongPtrW',user.GetWindowLongW);set_=getattr(user,'SetWindowLongPtrW',user.SetWindowLongW)
            get.argtypes=[c.c_void_p,c.c_int];get.restype=c.c_ssize_t;set_.argtypes=[c.c_void_p,c.c_int,c.c_ssize_t];set_.restype=c.c_ssize_t
            hwnd=user.GetParent(tip.winfo_id())
            if hwnd:set_(hwnd,-20,get(hwnd,-20)|0x08000000|0x00000080)
        except (AttributeError,OSError):pass

    def hide(self,event=None):
        for name in ('job','layout_job'):
            job=getattr(self,name)
            if job:
                try:self.widget.after_cancel(job)
                except tk.TclError:pass
                setattr(self,name,None)
        if self.owner_binding:
            owner,binding=self.owner_binding;self.owner_binding=None
            try:owner.unbind('<Configure>',binding)
            except tk.TclError:pass
        tip=self.tip;self.tip=None
        if getattr(self.theme,'active_hover_hint',None) is self:self.theme.active_hover_hint=None
        if hasattr(self.widget,'tip'):self.widget.tip=None
        if tip is not None:
            try:tip.destroy()
            except tk.TclError:pass

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
