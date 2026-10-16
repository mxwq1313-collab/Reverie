"""Resident nonmodal sidebar: docked at wide sizes, a right drawer at narrow sizes."""
import tkinter as tk
from tkinter import ttk
from .theme import PAPER,LINE,CANVAS
from .layout_config import configure_changed


class CopilotShell:
    def build_copilot_host(self):
        u=self.theme.u;layout=self.controller.copilot_layout()
        self.copilot_expanded=layout['expanded'];self.copilot_width=layout['width'];self.copilot_mode='hidden'
        self.copilot_host=ttk.Frame(self.workspace_panes,width=u(self.copilot_width))
        self.copilot_host._ai_surface=True;self.copilot_host.grid_propagate(False);self.copilot_host.rowconfigure(1,weight=1);self.copilot_host.columnconfigure(1,weight=1)
        grip=tk.Frame(self.copilot_host,width=u(3),background=CANVAS,cursor='sb_h_double_arrow')
        grip.grid(row=0,column=0,rowspan=2,sticky='ns')
        grip.bind('<Button-1>',self.start_copilot_drag);grip.bind('<B1-Motion>',self.drag_copilot);grip.bind('<ButtonRelease-1>',lambda _:self.persist_copilot_layout())
        header=ttk.Frame(self.copilot_host,padding=(u(16),u(16)));header.grid(row=0,column=1,sticky='ew');header.columnconfigure(0,weight=1)
        self.copilot_header=header;header.rowconfigure(0,minsize=self.theme.control_height)
        self.copilot_title=ttk.Label(header,text='Codex',font=self.theme.section);self.copilot_title.grid(row=0,column=0,sticky='w')
        self.copilot_hide_button=self.icon(header,'close','收起 Codex',self.hide_copilot);self.copilot_hide_button.configure(style='AiQuiet.TButton');self.copilot_hide_button.grid(row=0,column=1,sticky='e')
        privacy=ttk.Label(header,text='提问及相关归档片段会发送给 OpenAI',style='Hint.TLabel',wraplength=u(300));privacy.grid(row=1,column=0,columnspan=2,sticky='w',pady=(u(3),0))
        header.bind('<Configure>',lambda event:configure_changed(privacy,wraplength=max(u(180),event.width-u(32))),add='+')
        self.copilot_body=ttk.Frame(self.copilot_host,padding=(u(16),0,u(16),u(8)))
        self.copilot_body.grid(row=1,column=1,sticky='nsew')
        self.workspace_panes.bind('<ButtonRelease-1>',self.save_copilot_sash,add='+')

    def layout_copilot(self):
        if not hasattr(self,'copilot_host'):return
        panes=self.workspace_panes;u=self.theme.u
        width=max(self.resize_viewport.winfo_width(),u(700))
        threshold=940 if self.copilot_mode=='docked' else 1020 if self.copilot_mode=='drawer' else 980
        mode='docked' if width/self.theme.scale>=threshold else 'drawer'
        if not self.copilot_expanded:mode='hidden'
        if mode!=self.copilot_mode:
            panes.forget(self.copilot_host);self.copilot_host.place_forget()
            if mode=='docked':panes.add(self.copilot_host,minsize=u(300),stretch='never')
            self.copilot_mode=mode
        if mode=='docked':
            desired=min(u(self.copilot_width),max(u(300),width-u(606)))
            target=width-desired-u(2)
            if abs(panes.sash_coord(0)[0]-target)>1:panes.sash_place(0,target,0)
        elif mode=='drawer':
            desired=min(u(self.copilot_width),max(u(300),width-u(80)))
            self.copilot_host.place(relx=1,anchor='ne',y=0,width=desired,relheight=1);self.copilot_host.lift()
        self.copilot_button.toggled=self.copilot_expanded;self.copilot_button.refresh_icon()

    def open_copilot(self,focus=True):
        changed=not self.copilot_expanded;self.copilot_expanded=True;self.adapt_layout()
        if changed:self.persist_copilot_layout()
        if focus:self.root.after_idle(self.focus_copilot_input)

    def focus_copilot_input(self):
        if not self.closed:self.agent_panel.input.focus_set()

    def hide_copilot(self):
        self.copilot_expanded=False;self.adapt_layout();self.persist_copilot_layout();self.leave_copilot_input()

    def toggle_copilot(self):
        if self.copilot_expanded:self.hide_copilot()
        else:self.open_copilot()

    def copilot_shortcut(self,event=None):
        self.open_copilot();return 'break'

    def ask_current_conversation(self):
        self.agent_panel.scope.set('当前会话');self.open_copilot()

    def notify_copilot_binding(self):
        """Revoke before any potentially slow main-reader query starts."""
        panel=getattr(self,'agent_panel',None)
        if panel is None or panel.client is None:return
        try:
            scope=panel.current_scope();binding=(scope.key,self.controller.archive_view_token())
        except Exception:binding=None
        if binding!=getattr(panel,'observed_binding',None):
            panel.client.revoke_tools();panel.retry_request=None;panel.observed_binding=binding

    def leave_copilot_input(self):
        target=self.chat_text.canvas if self.current_page=='聊天归档' else self.pages[self.current_page]
        target.focus_set()

    def persist_copilot_layout(self):
        try:
            self.controller.save_copilot_layout(self.copilot_expanded,self.copilot_width)
            if hasattr(self,'show_ai_setting'):self.show_ai_setting.set(self.copilot_expanded)
        except OSError:self.status.set('助手布局未能保存；当前显示仍可使用。')

    def save_copilot_sash(self,event=None):
        if self.copilot_mode=='docked':
            sash=self.workspace_panes.sash_coord(0)[0]
            self.copilot_width=max(300,min(640,round((self.workspace_panes.winfo_width()-sash-self.theme.u(2))/self.theme.scale)))
            self.persist_copilot_layout()

    def start_copilot_drag(self,event):
        self.copilot_drag=(event.x_root,self.copilot_host.winfo_width()/self.theme.scale)

    def drag_copilot(self,event):
        start,width=self.copilot_drag
        self.copilot_width=max(300,min(640,round(width+(start-event.x_root)/self.theme.scale)))
        self.layout_copilot()
