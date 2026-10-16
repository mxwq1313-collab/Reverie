"""A small nonmodal memory utility anchored beside the lower navigation rail."""
import tkinter as tk
from tkinter import ttk


class MemoryPopup:
    def __init__(self,app):
        self.app=app;self.return_focus=None
        self.window=tk.Toplevel(app.root);self.window.withdraw()
        self.window.title('随机回忆 · 思绪');self.window.transient(app.root)
        self.window.protocol('WM_DELETE_WINDOW',self.hide)
        self.window.bind('<Escape>',lambda _:self.hide())
        self.content=ttk.Frame(self.window,padding=app.theme.u(20))
        self.content.pack(fill='both',expand=True)

    def toggle(self):
        if self.window.winfo_viewable():self.hide()
        else:self.open()

    def open(self):
        app=self.app
        if app.closed:return
        if self.window.winfo_viewable():self.window.lift();return
        self.return_focus=app.root.focus_get()
        tool=app.toolbox_panel.random;tool.refresh_context()
        app.theme.apply_tree(self.window);app.localizer.apply(self.window,())
        self.window.title('Random memory · Sixu' if app.localizer.language=='en_US' else '随机回忆 · 思绪')
        u=app.theme.u
        width=min(u(max(520,app.theme.text_size*25)),app.root.winfo_screenwidth()-u(32))
        height=min(u(600 if app.theme.text_size<=18 else 720),app.root.winfo_screenheight()-u(80))
        x=max(u(8),min(app.nav.winfo_rootx()+app.nav.winfo_width()+u(10),app.root.winfo_screenwidth()-width-u(12)))
        y=max(u(12),min(app.memory_button.winfo_rooty()+app.memory_button.winfo_height()-height,app.root.winfo_screenheight()-height-u(45)))
        self.window.geometry(f'{width}x{height}+{x}+{y}')
        self.window.minsize(min(u(460),width),min(u(480),height))
        self.window.deiconify();self.window.lift();tool.search_button.focus_set()
        app.memory_button.toggled=True;app.memory_button.refresh_icon()

    def hide(self,restore_focus=True):
        self.window.withdraw()
        app=self.app;app.memory_button.toggled=False;app.memory_button.refresh_icon()
        if restore_focus:
            target=self.return_focus
            if target is not None and target.winfo_exists():target.focus_set()
            else:app.memory_button.focus_set()
