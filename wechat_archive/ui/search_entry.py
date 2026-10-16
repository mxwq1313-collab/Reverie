"""Filled native entries with presentation-only placeholders and Enter submission."""
import tkinter as tk
from tkinter import ttk


class SearchEntry(ttk.Entry):
    def __init__(self,parent,theme,variable,placeholder,submit):
        super().__init__(parent,textvariable=variable,style='Search.TEntry',width=1)
        self.theme=theme;self.variable=variable
        self.placeholder_label=tk.Label(self,text=placeholder,font=theme.body,background=theme.palette['CANVAS'],foreground=theme.palette['SECONDARY'],borderwidth=0,cursor='xterm')
        self.placeholder_label.bind('<Button-1>',lambda _:self.focus_set())
        def refresh(*_):
            if not self.winfo_exists():return
            if not variable.get() and str(self.tk.call('focus'))!=str(self):self.placeholder_label.place(x=theme.u(12),rely=.5,anchor='w')
            else:self.placeholder_label.place_forget()
        self.refresh_placeholder=refresh;self.placeholder_trace=variable.trace_add('write',refresh)
        self.bind('<FocusIn>',refresh,add='+');self.bind('<FocusOut>',refresh,add='+')
        def enter(_):submit();return 'break'
        self.bind('<Return>',enter)
        def cleanup(event):
            if event.widget is self:
                try:variable.trace_remove('write',self.placeholder_trace)
                except tk.TclError:pass
        self.bind('<Destroy>',cleanup,add='+');refresh()
