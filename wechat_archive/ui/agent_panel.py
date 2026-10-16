"""软件内 Codex 插件：官方登录、范围选择、流式对话和查询回执。"""

import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from tkinter.scrolledtext import ScrolledText
import webbrowser
import re
from pathlib import Path

from ..agent import ArchiveScope, CodexClient
from ..agent.client import find_codex, login_url
from ..errors import ValidationError
from .common_widgets import Collapsible
from .model_controls import ModelControls,EFFORT_LABELS
from .history_panel import HistoryMixin
from .theme import ACCENT, INK, SECONDARY
from .task_status import tool_status


class AgentPanel(HistoryMixin,ModelControls):
    def __init__(self, app, page, client_factory=CodexClient, open_browser=webbrowser.open, compact=False):
        self.app = app; self.root = app.root
        self.client_factory = client_factory; self.open_browser = open_browser
        self.client = None; self.busy = False; self.active = False; self.closed = False
        self.generation = 0; self.events = queue.Queue(); self.messages = []; self.by_id = {}
        self.archive_path = None; self.last_scope = None; self.model_ids = {}
        self.authenticated = False; self.scope_labels = {}; self.scope_labels_key = None
        self.pending_request=None;self.retry_request=None
        self.compact=compact
        self.initialize_history()
        from ..ai import ContextProvider,AIService
        self.ai_service=AIService(ContextProvider(app));self.last_context=None
        if compact:
            from .copilot_panel import build_compact
            build_compact(self,page)
        else:
            app.title(page,'Codex 助手','在软件内登录 ChatGPT、查询并分析已归档私聊。登录在 OpenAI 官方浏览器页面完成；提问及查询到的文字会发送给 OpenAI，并使用账号可用额度。')
            self.steps = tk.StringVar(self.root,value='1 连接   →   2 登录   →   3 选择归档范围   →   4 提问')
            ttk.Label(page,textvariable=self.steps,style='Hint.TLabel').pack(anchor='w',pady=(0,5))
            self.advanced = Collapsible(page,'运行组件设置',app.theme);self.advanced.pack(fill='x')
            row = ttk.Frame(self.advanced.content); row.pack(fill='x',pady=(0,5))
            self.binary = tk.StringVar(self.root)
            try: self.binary.set(str(find_codex()))
            except Exception: pass
            ttk.Label(row,text='运行组件').pack(side='left')
            ttk.Entry(row,textvariable=self.binary,state='readonly').pack(side='left',fill='x',expand=True,padx=8)
            self.pick_button = ttk.Button(row,text='选择 codex.exe',command=self.pick_binary); self.pick_button.pack(side='left')
            row = ttk.Frame(page); row.pack(fill='x',pady=5)
            self.connect_button = ttk.Button(row,text='连接 Codex',command=self.connect); self.connect_button.pack(side='left')
            self.login_button = ttk.Button(row,text='登录 ChatGPT',command=self.login); self.login_button.pack(side='left',padx=8)
            self.cancel_login_button = ttk.Button(row,text='取消登录',command=self.cancel_login); self.cancel_login_button.pack(side='left')
            row=ttk.Frame(page);row.pack(fill='x',pady=(0,4))
            self.logout_button = ttk.Button(row,text='退出登录',command=self.logout); self.logout_button.pack(side='left',padx=8)
            self.account_button = ttk.Button(row,text='检查登录状态',command=self.refresh_account);self.account_button.pack(side='left')
            self.account_text = tk.StringVar(self.root,value='未连接 · 使用插件独立的登录状态')
            ttk.Label(page,textvariable=self.account_text,wraplength=920).pack(anchor='w',pady=5)
            row = ttk.Frame(page); row.pack(fill='x',pady=5)
            ttk.Label(row,text='读取范围').pack(side='left')
            self.scope = tk.StringVar(self.root,value='当前会话')
            self.scope_box = ttk.Combobox(row,textvariable=self.scope,values=('当前会话','当前身份的所有私聊'),state='readonly',width=22)
            self.scope_box.pack(side='left',padx=8)
            row=ttk.Frame(page);row.pack(fill='x',pady=(0,4))
            ttk.Label(row,text='模型').pack(side='left')
            self.model = tk.StringVar(self.root,value='自动（账号默认模型）')
            self.model_box = ttk.Combobox(row,textvariable=self.model,values=('自动（账号默认模型）',),state='readonly',width=28)
            self.model_box.pack(side='left',padx=8)
            self.models_button = ttk.Button(row,text='刷新模型',command=self.refresh_models); self.models_button.pack(side='left')
            self.new_button = ttk.Button(row,text='新对话',command=self.new_conversation); self.new_button.pack(side='left',padx=8)
            self.scope_text = tk.StringVar(self.root,value='请在“聊天归档”选择查看身份和联系人。')
            ttk.Label(page,textvariable=self.scope_text,wraplength=920,style='Hint.TLabel').pack(anchor='w',pady=5)
            actions=ttk.Frame(page);actions.pack(fill='x',pady=(3,0))
            self.copy_button=ttk.Button(actions,text='复制最近回答',command=self.copy_answer);self.copy_button.pack(side='left')
            self.export_button=ttk.Button(actions,text='保存当前对话',command=self.export_conversation);self.export_button.pack(side='left',padx=8)
            ttk.Label(actions,text='点击消息引用可回查原文',style='Hint.TLabel').pack(side='right')
            self.transcript = ScrolledText(page,height=11,wrap='word',font=app.theme.body,background='#fff',padx=12,pady=10)
            app.theme.text_surface(self.transcript)
            self.transcript.pack(fill='both',expand=True,pady=6); self.transcript.configure(state='disabled')
            self.transcript.tag_configure('role',foreground=ACCENT,font=app.theme.name,spacing1=8,spacing3=4)
            self.transcript.tag_configure('system',foreground=SECONDARY)
            self.transcript.tag_configure('reference',foreground=ACCENT,underline=True)
            follow_row=ttk.Frame(page);follow_row.pack(fill='x')
            self.latest_button=ttk.Button(follow_row,text='回到最新',command=self.jump_latest,state='disabled');self.latest_button.pack(side='right')
            self.transcript.configure(yscrollcommand=self.transcript_scrolled)
            ttk.Label(page,text='例如：找出我们讨论论文修改的消息，并按时间整理待办；给出原记录引用。',style='Hint.TLabel',wraplength=920).pack(anchor='w')
            prompts=ttk.Frame(page);prompts.pack(fill='x',pady=(4,0))
            for label,prompt in (('整理待办','请从当前授权会话提取待办，列出负责人、时间和原消息引用。'),('按时间总结','请按时间总结当前授权会话的主要讨论，区分原话与归纳，并附消息引用。'),('查找原消息','请查找当前授权会话中关于【关键词】的原消息，保留原文并附时间和引用。')):
                ttk.Button(prompts,text=label,command=lambda text=prompt:self.fill_prompt(text)).pack(side='left',padx=(0,6))
            self.input = ScrolledText(page,height=3,wrap='word',font=app.theme.body); self.input.pack(fill='x',pady=5)
            app.theme.text_surface(self.input,editable=True,framed=True)
            self.input.bind('<Control-Return>',self.send_shortcut)
            self.input.bind('<<Modified>>',self.input_changed)
            row = ttk.Frame(page); row.pack(fill='x')
            self.send_button = ttk.Button(row,text='发送',command=self.send,style='Primary.TButton'); self.send_button.pack(side='left')
            self.stop_button = ttk.Button(row,text='停止回答',command=self.stop); self.stop_button.pack(side='left',padx=8)
            self.state = tk.StringVar(self.root,value='查询工具只读；不会编辑归档或发送微信消息。')
            ttk.Label(row,textvariable=self.state,wraplength=710).pack(side='left',padx=8)
            self.gate_hint=tk.StringVar(self.root,value='先连接并登录，再选择会话。Ctrl+Enter发送；Enter换行。')
            ttk.Label(page,textvariable=self.gate_hint,style='Hint.TLabel',wraplength=900).pack(anchor='w',pady=(4,0))
            recovery=ttk.Frame(page);recovery.pack(fill='x',pady=4)
            self.retry_button=ttk.Button(recovery,text='重新发送失败问题',command=self.retry_question);self.retry_button.pack(side='left')
            self.edit_question_button=ttk.Button(recovery,text='取回问题编辑',command=self.edit_failed_question);self.edit_question_button.pack(side='left',padx=8)
        if not compact:
            self.init_inference();row=ttk.Frame(page);row.pack(fill='x')
            self.effort_box=ttk.Combobox(row,textvariable=self.effort,state='readonly',values=tuple(self.effort_ids));self.effort_box.pack(side='left')
            ttk.Checkbutton(row,text='快速模式',variable=self.fast_mode).pack(side='left')
        self.reply_indicator=tk.StringVar(self.root)
        self.reply_indicator_label=ttk.Label(page,textvariable=self.reply_indicator,style='Hint.TLabel')
        self.reply_job=None;self.reply_frame=0;self.follow_job=None
        self.transcript.bind('<Configure>',self.schedule_dialogue_layout,add='+')
        self.layout_dialogue()
        self._controls()
        self.poll_job = self.root.after(60 if self.busy or self.active else 400,self.poll)

    def layout_dialogue(self):
        u=self.app.theme.u;width=max(u(200),self.transcript.winfo_width())
        key=(str(self.transcript),width//4,self.app.theme.generation,self.app.theme.body)
        if key==getattr(self,'dialogue_layout_key',None):return
        self.dialogue_layout_key=key
        self.transcript.tag_configure('turn_user',justify='right',lmargin1=max(u(28),int(width*.22)),lmargin2=max(u(28),int(width*.22)),rmargin=u(12),spacing1=u(13),spacing3=u(13),background=self.app.theme.palette['OWN'])
        self.transcript.tag_configure('turn_codex',justify='left',lmargin1=u(10),lmargin2=u(10),rmargin=u(14),spacing1=u(2),spacing3=u(3),background=self.app.theme.palette['PAPER'])
        self.transcript.tag_configure('turn_system',justify='left',foreground=self.app.theme.palette['SECONDARY'])
        from .rich_markdown import configure
        configure(self.transcript,self.app.theme)

    def schedule_dialogue_layout(self,event=None):
        if self.closed:return
        if event is not None and getattr(self,'dialogue_width',None)==event.width:return
        if event is not None:self.dialogue_width=event.width
        if getattr(self,'dialogue_layout_job',None):self.root.after_cancel(self.dialogue_layout_job)
        def layout():
            self.dialogue_layout_job=None
            if not self.closed:self.layout_dialogue()
        self.dialogue_layout_job=self.root.after(40,layout)

    def sync_reply_indicator(self):
        if self.active and not self.closed:
            if not self.reply_indicator_label.winfo_manager():
                if self.compact:self.reply_indicator_label.grid(row=3,column=0,sticky='w',pady=(self.app.theme.u(4),0))
                else:self.reply_indicator_label.pack(anchor='w')
            if self.reply_job is None:self.animate_reply()
        else:
            if self.reply_job:self.root.after_cancel(self.reply_job)
            self.reply_job=None;self.reply_indicator.set('');self.reply_indicator_label.grid_remove() if self.compact else self.reply_indicator_label.pack_forget()

    def animate_reply(self):
        self.reply_job=None
        if not self.active or self.closed:return
        title=self.app.tr('千丝万绪…').rstrip('….')
        dots='.'*(self.reply_frame%3+1)
        self.reply_indicator.set(title+dots)
        self.reply_frame+=1
        self.reply_job=self.root.after(650 if self.app.ui_settings['reduce_motion'] else 360,self.animate_reply)

    def set_control_state(self,widget,state):
        if str(widget.cget('state'))!=state:widget.configure(state=state)

    def _controls(self):
        self.sync_reply_indicator()
        connected = self.client is not None and self.client.connected
        free = not self.busy and not self.active and not self.app.busy
        for widget in (self.pick_button,self.connect_button): self.set_control_state(widget,'normal' if free else 'disabled')
        self.set_control_state(self.login_button,'normal' if connected and free and not self.authenticated else 'disabled')
        self.set_control_state(self.logout_button,'normal' if connected and free and self.authenticated else 'disabled')
        for widget in (self.models_button,self.account_button):self.set_control_state(widget,'normal' if connected and free else 'disabled')
        self.set_control_state(self.cancel_login_button,'normal' if connected and free and self.client.login_id else 'disabled')
        self.set_control_state(self.new_button,'normal' if free else 'disabled')
        try:self.current_scope();valid_scope=True
        except Exception:valid_scope=False
        text=self.input.get('1.0','end').strip()
        self.set_control_state(self.send_button,'normal' if connected and self.authenticated and valid_scope and text and free else 'disabled')
        if not connected:self.gate_hint.set('先到设置连接 Codex 并登录 ChatGPT，再选择归档会话。')
        elif not self.authenticated:self.gate_hint.set('连接已建立，尚未登录；请完成官方授权或检查登录状态。')
        elif not valid_scope:self.gate_hint.set('请在聊天归档选择身份和会话，再回到这里提问。')
        elif self.active:self.gate_hint.set('正在回答；可停止回答后继续。当前读取范围固定。')
        else:self.gate_hint.set('范围已就绪。Ctrl+Enter发送；Enter换行。快捷问题只填入，不自动发送。')
        self.set_control_state(self.copy_button,'normal' if any(item['role'].startswith('Codex') and item['text'] for item in self.messages) else 'disabled')
        self.set_control_state(self.export_button,'normal' if self.messages and free else 'disabled')
        self.set_control_state(self.stop_button,'normal' if self.active and not self.busy else 'disabled')
        self.set_control_state(self.scope_box,'readonly' if free else 'disabled')
        for widget in (self.model_box,self.effort_box):self.set_control_state(widget,'readonly' if not self.app.busy else 'disabled')
        if hasattr(self,'fast_button'):self.set_control_state(self.fast_button,'normal' if not self.app.busy else 'disabled')
        retry_valid=self.request_matches(self.retry_request)
        self.set_control_state(self.retry_button,'normal' if retry_valid and free and connected and self.authenticated else 'disabled')
        self.set_control_state(self.edit_question_button,'normal' if retry_valid and free else 'disabled')
        if self.compact:
            if self.messages:self.empty_notice.place_forget()
            elif not self.empty_notice.winfo_manager():self.empty_notice.place(relx=.5,rely=.35,anchor='center')
            self.app.localizer.text(self.start_button,'连接 Codex' if not connected else '登录 ChatGPT' if not self.authenticated else '开始提问')
            if self.active:
                if self.send_button.winfo_manager():self.send_button.pack_forget()
                if not self.stop_button.winfo_manager():self.stop_button.pack(side='right')
            else:
                if self.stop_button.winfo_manager():self.stop_button.pack_forget()
                if not self.send_button.winfo_manager():self.send_button.pack(side='right')

    def start_action(self):
        if not self.client or not self.client.connected:self.refresh_models()
        elif not self.authenticated:self.login()
        else:self.input.focus_set()

    def run(self, work, done):
        if self.busy or self.closed:
            return
        self.busy = True; self._controls(); generation = self.generation
        def execute():
            try: self.events.put({'kind':'done','value':work(),'callback':done,'generation':generation})
            except Exception as error: self.events.put({'kind':'failed','message':str(error),'generation':generation})
        threading.Thread(target=execute,name='codex-ui-operation',daemon=True).start()

    def pick_binary(self):
        path = filedialog.askopenfilename(parent=self.root,title='选择官方 Codex 运行组件',filetypes=[('Codex','codex.exe')])
        if path:
            self.binary.set(path)
            self.save_configuration()
            if self.client: self.client.close(); self.client = None
            self._clear(); self.account_text.set('运行组件已更换，请重新连接。'); self._controls()

    def save_configuration(self):
        settings=self.app.controller.settings();old=settings.get('ai',{})
        settings['ai']={**(old if isinstance(old,dict) else {}),'codex_executable':self.binary.get(),'scope':self.scope.get(),'model':self.model.get(),'model_id':self.model_ids.get(self.model.get()),'effort':self.effort_ids.get(self.effort.get()),'fast_mode':self.fast_mode.get(),'model_catalog':self.model_catalog,'runtime_revision':getattr(self,'runtime_revision',None),'preferred_model_applied':getattr(self,'preferred_model_applied',False)}
        self.app.controller.save_settings(settings)

    def connect(self):
        saved=self.retry_request if self.request_matches(self.retry_request) else None
        if self.client: self.client.close()
        self.generation += 1; generation = self.generation; self._clear();self.authenticated=False
        self.retry_request=saved
        self.client = self.client_factory(self.app.controller.profile_dir,executable=self.binary.get() or None,
            event_sink=lambda event:self.events.put({**event,'generation':generation}))
        self.state.set('正在启动 Codex…')
        self.run(self.client.start,self._account)

    def _account(self, result):
        account = result.get('account')
        self.authenticated=bool(account and account.get('type')=='chatgpt')
        if self.client and self.client.connected and not self.catalog_ready:self.root.after_idle(self.refresh_models)
        if account and account.get('type') == 'chatgpt':
            self.account_text.set(f"已登录 · {account.get('email') or 'ChatGPT 账号'} · {account.get('planType','未知套餐')}")
            self.state.set('账号已连接；模型能否使用以实际请求结果为准。')
        else:
            self.account_text.set('未登录 · 点击“登录 ChatGPT”，在官方页面完成授权')
            self.state.set('Codex 已连接；请登录后提问。')

    def refresh_account(self):
        if self.client and self.client.connected:
            self.state.set('正在检查登录状态…');self.run(self.client.account,self._account)

    def fill_prompt(self,text):
        if self.busy or self.active:return
        self.input.delete('1.0','end');self.input.insert('1.0',text);self.input.focus_set();self._controls()

    def input_changed(self,event=None):
        if self.input.edit_modified():
            self.input.edit_modified(False);self._controls()

    def send_shortcut(self,event=None):
        self.send();return 'break'

    def leave_input(self,event=None):
        if hasattr(self.app,'leave_copilot_input'):self.app.leave_copilot_input()
        return 'break'

    def copy_answer(self):
        answer=next((item['text'] for item in reversed(self.messages) if item['role'].startswith('Codex') and item['text']),None)
        if answer is None:self.state.set('当前没有可复制的回答。');return
        self.root.clipboard_clear();self.root.clipboard_append(answer);self.state.set('最近回答已复制，引用编号保留。')

    def conversation_text(self):
        return '思绪 · Codex 对话\n'+self.scope_text.get()+'\n\n'+'\n\n'.join(item['role']+'\n'+item['text'] for item in self.messages)

    def export_conversation(self):
        if not self.messages:self.state.set('当前没有可保存的对话。');return
        path=filedialog.asksaveasfilename(parent=self.root,title='保存当前对话到新文件',defaultextension='.txt',initialfile='Codex对话.txt',filetypes=[('UTF-8文本','*.txt')])
        if not path:return
        try:
            with Path(path).open('x',encoding='utf-8',newline='\n') as stream:stream.write(self.conversation_text()+'\n')
        except OSError as error:self.state.set('保存未完成：'+str(error));return
        self.state.set('当前对话已保存。')

    def open_reference(self,message_id):
        try:
            scope=self.current_scope()
            if not self.client or not self.client.tools or self.client.tools.scope.key!=scope.key:
                raise ValidationError('当前范围没有可回查的工具，请在选定会话中重新查询。')
            item=self.client.tools.archive_message(message_id,content_limit=8000)['item']
            window=tk.Toplevel(self.root);window.title('原消息回查');window.geometry('640x420')
            ttk.Label(window,text=f"消息 #{item['id']} · {item['display_time']} · {item['sender_name']} → {item['receiver_name']}",wraplength=600).pack(fill='x',padx=15,pady=12)
            text=ScrolledText(window,wrap='word',font=self.app.theme.body);text.pack(fill='both',expand=True,padx=15,pady=(0,12))
            self.app.theme.text_surface(text)
            text.insert('1.0',item['content']+('\n\n[原文超过此窗口片段，完整内容请在聊天归档查看。]' if item['content_truncated'] else ''));text.configure(state='disabled')
            self.state.set('已回查当前授权范围的原文，请对照模型结论。')
            return window
        except Exception as error:self.state.set('引用无法展开：'+str(error));return None

    def login(self):
        self.state.set('正在请求官方登录页面…')
        def done(result):
            url = login_url(result['authUrl'])
            if self.open_browser(url):
                self.state.set('请在浏览器完成登录，账号状态将自动返回。')
            else:
                self.state.set('浏览器未能打开。请重试登录或检查系统默认浏览器。')
        self.run(self.client.login,done)

    def cancel_login(self):
        self.run(self.client.cancel_login,lambda _:self.state.set('登录已取消。'))

    def logout(self):
        def done(_): self._clear(); self._account({'account':None})
        self.run(self.client.logout,done)

    def refresh_models(self):
        if not self.client or not self.client.connected:self.connect();self.root.after(100,self.refresh_after_connect);return
        self.state.set('正在读取模型目录…')
        def done(models):
            self.set_catalog(models)
            self.state.set('模型目录已更新；列出模型不等于账号已经验证可用。')
            self.save_configuration();self.app.localize_ui()
        self.run(self.client.models,done)

    def refresh_after_connect(self):
        if self.closed:return
        if self.busy:self.root.after(100,self.refresh_after_connect);return
        if self.client and self.client.connected:self.refresh_models()

    def current_scope(self):
        path = self.app.controller.require_archive()
        owner = self.app.owner_id; peer = self.app.peer_id if self.scope.get() == '当前会话' else None
        if owner is None or self.scope.get() == '当前会话' and peer is None:
            raise ValidationError('请先在“聊天归档”选择查看身份和联系人。')
        return ArchiveScope(path,owner,peer)

    def send(self,*,task_text=None):
        if self.active or self.busy:
            return
        try:
            if self.app.busy:raise ValidationError('归档操作进行中，请完成后再提问。')
            scope = self.current_scope(); display_text = self.input.get('1.0','end').strip()
            if not display_text or len(display_text)>12000: raise ValidationError('请输入 1–12000 字的提问。')
            text=task_text if task_text is not None else display_text
            if not self.client or not self.client.connected:raise ValidationError('请先连接 Codex。')
            if not self.authenticated:raise ValidationError('请先完成 ChatGPT 登录，再发送问题。')
            model=self.selected_model()
            request=self.ai_service.prepare(text,scope,model,expected_epoch=self.client.scope_epoch,effort=self.selected_effort(),fast_mode=self.fast_mode.get())
        except Exception as error:
            self.state.set(str(error)); return
        model = self.selected_model(); key = scope.key
        if key != self.last_scope:
            self._clear(); self.last_scope = key
        self.last_context=request.context
        self.pending_request={'question':display_text,'task_text':task_text,'scope':scope.key,'token':self.app.controller.archive_view_token(),'model':self.model.get(),'effort':self.effort.get(),'fast_mode':self.fast_mode.get()}
        self.retry_request=None
        self._add('你',display_text)
        self.input.delete('1.0','end'); self.active = True; self.state.set('Codex 正在查询与回答…')
        def done(result):
            if result.get('_ai_context') is not None:self.last_context=result['_ai_context']
            if result['turn'].get('status') in ('completed','failed','interrupted'):
                self.active = False
                if result['turn'].get('status')!='completed':self.remember_failed_question()
        self.run(lambda:self.ai_service.send(self.client,request),done)

    def stop(self):
        self.state.set('正在停止回答…')
        self.run(self.client.interrupt,lambda _:self.state.set('停止请求已发送，等待回合结束。') if self.active else None)

    def new_conversation(self):
        self.flush_history()
        if self.client: self.client.new_conversation()
        self._clear(); self.state.set('已开启新对话。')

    def _clear(self):
        self.flush_history();self.history_id=None;self.history_meta=None;self.history_viewing=False
        self.messages = []; self.by_id = {}; self.last_scope = None; self.active = False
        self.pending_request=None;self.retry_request=None
        self.last_context=None
        self._render()

    def request_matches(self,request,check_options=True):
        if not request:return False
        try:
            return request['scope']==self.current_scope().key and request['token']==self.app.controller.archive_view_token() and (not check_options or request['model']==self.model.get() and request.get('effort',self.effort.get())==self.effort.get() and request.get('fast_mode',self.fast_mode.get())==self.fast_mode.get())
        except Exception:return False

    def remember_failed_question(self):
        if self.request_matches(self.pending_request):self.retry_request=dict(self.pending_request)

    def edit_failed_question(self):
        if self.busy or self.active:return
        if not self.request_matches(self.retry_request):
            self.retry_request=None;self.state.set('归档、范围或模型已变化，请在新范围重新提问。');self._controls();return
        self.fill_prompt(self.retry_request['question']);self.state.set('失败问题已取回，可编辑后发送。')

    def retry_question(self):
        if self.busy or self.active:return
        if not self.request_matches(self.retry_request):
            self.retry_request=None;self.state.set('归档、范围或模型已变化，旧问题不能自动重试。');self._controls();return
        task_text=self.retry_request.get('task_text')
        self.fill_prompt(self.retry_request['question']);self.send(task_text=task_text)

    def _add(self, role, text, item_id=None):
        value = {'role':role,'text':text}; self.messages.append(value)
        if item_id: self.by_id[item_id] = value
        self._render()

    def _render(self):
        self._stream_dirty=False
        self.layout_dialogue()
        self.queue_history()
        text = '\n\n'.join(item['text'] for item in self.messages)
        if len(text)>2000000:
            text = '较早的显示内容已折叠，请开启新对话以减少上下文。\n\n'+text[-2000000:]
        previous=self.transcript.get('1.0','end-1c')
        follow=not previous or self.transcript.yview()[1]>=.995
        self.transcript.mark_set('ux_reader','@0,0');self.transcript.mark_gravity('ux_reader','left')
        prefix=0;suffix=0
        if text.startswith(previous):prefix=len(previous)
        else:
            while prefix<min(len(previous),len(text)) and previous[prefix]==text[prefix]:prefix+=1
            while suffix<min(len(previous),len(text))-prefix and previous[-suffix-1]==text[-suffix-1]:suffix+=1
        length=len
        start=f'1.0+{length(previous[:prefix])}c'
        end=f'1.0+{length(previous[:len(previous)-suffix])}c'
        self.transcript.configure(state='normal')
        if previous!=text:
            self.transcript.delete(start,end)
            self.transcript.insert(start,text[prefix:len(text)-suffix] if suffix else text[prefix:])
        self.transcript.tag_remove('role','1.0','end')
        for tag in ('turn_user','turn_codex','turn_system'):self.transcript.tag_remove(tag,'1.0','end')
        cursor=0
        if len(text)<2000000:
            for item in self.messages:
                part=item['text']
                start=f'1.0+{length(text[:cursor])}c';end=f'{start}+{length(part)}c'
                tag='turn_user' if item['role'] in ('你','You') else 'turn_codex' if item['role'].startswith('Codex') else 'turn_system'
                self.transcript.tag_add(tag,start,end);cursor+=len(part)+2
        for tag in self.transcript.tag_names():
            if tag.startswith('reference_'):self.transcript.tag_delete(tag)
        for index,line in enumerate(text.splitlines(),1):
            for match in re.finditer(r'\[消息 #(\d+)\]',line):
                tag='reference_'+str(index)+'_'+str(match.start())
                self.transcript.tag_add(tag,f'{index}.0+{length(line[:match.start()])}c',f'{index}.0+{length(line[:match.end()])}c')
                self.transcript.tag_configure(tag,foreground=self.app.theme.palette['ACCENT'],underline=True,font=self.app.theme.small)
                self.transcript.tag_bind(tag,'<Enter>',lambda _:self.transcript.configure(cursor='hand2'))
                self.transcript.tag_bind(tag,'<Leave>',lambda _:self.transcript.configure(cursor='xterm'))
                self.transcript.tag_bind(tag,'<Button-1>',lambda event,number=int(match[1]):self.open_reference(number))
        from .rich_markdown import decorate
        decorate(self.transcript,text,self.app.theme)
        self.transcript.configure(state='disabled')
        if follow:
            self.jump_latest()
            if self.follow_job:self.root.after_cancel(self.follow_job)
            self.follow_job=self.root.after_idle(self.follow_latest)
        else:self.transcript.yview('ux_reader')

    def follow_latest(self):
        self.follow_job=None
        if not self.closed:self.jump_latest()

    def transcript_scrolled(self,first,last):
        self.transcript.vbar.set(first,last)
        self.latest_button.configure(state='disabled' if float(last)>=.995 else 'normal')
        if self.compact:
            if float(last)>=.995 and self.latest_button.winfo_manager():self.latest_button.place_forget()
            elif float(last)<.995 and not self.latest_button.winfo_manager():self.latest_button.place(relx=1,rely=1,x=-self.app.theme.u(14),y=-self.app.theme.u(10),anchor='se')

    def jump_latest(self):
        self.transcript.see('end');self.latest_button.configure(state='disabled')

    def _notification(self, method, params):
        if self.pending_request and not self.request_matches(self.pending_request,False) and method not in ('account/login/completed','account/updated'):
            if method=='turn/completed':self.active=False
            return
        if method == 'turn/started':
            self.active = True
        elif method in ('account/login/completed','account/updated'):
            if method == 'account/login/completed' and not params.get('success'):
                self.state.set('登录未完成：'+str(params.get('error') or '已取消')); return
            if not self.busy:
                self.run(self.client.account,self._account)
            else:
                self.events.put({'kind':'refresh_account','generation':self.generation})
        elif method == 'item/agentMessage/delta':
            item_id = params['itemId']
            if item_id not in self.by_id: self._add('Codex','',item_id)
            self.by_id[item_id]['text'] += params.get('delta',''); self._stream_dirty=True
        elif method == 'item/completed' and params.get('item',{}).get('type') == 'agentMessage':
            item = params['item']; item_id = item['id']
            if item_id not in self.by_id: self._add('Codex','',item_id)
            self.by_id[item_id]['text'] = item.get('text','')
            self.by_id[item_id]['role'] = 'Codex · 回答' if item.get('phase') == 'final_answer' else 'Codex'
            self._render()
        elif method == 'turn/completed':
            self.active = False
            turn = params['turn']; status = turn.get('status')
            if status == 'completed':
                self.pending_request=None;self.retry_request=None;self.state.set('回答完成；请结合消息引用核对结论。')
            elif status == 'interrupted':
                self.remember_failed_question();self.state.set('回答已停止，现有内容保留但可能不完整；可取回问题或重试。')
            else:
                self.remember_failed_question()
                error = turn.get('error') or {}
                self.state.set('回答失败：'+str(error.get('message') or '连接、账号额度或模型请求失败'))
        elif method == 'error':
            self.state.set('Codex：'+str(params.get('error',{}).get('message','请求错误')))

    def poll(self):
        if self.closed: return
        refresh = False
        for _ in range(200):
            try: event = self.events.get_nowait()
            except queue.Empty: break
            if event.get('generation') != self.generation: continue
            kind = event['kind']
            try:
                if kind == 'done': self.busy = False; event['callback'](event['value'])
                elif kind == 'failed':
                    self.busy = False; self.active = bool(self.client and self.client.active)
                    self.state.set('未完成：'+event['message'])
                    self._add('系统',event['message'])
                    self.remember_failed_question()
                elif kind == 'conversation':
                    if self.history_meta is not None:self.history_meta['thread_id']=event['thread_id']
                elif kind == 'notification': self._notification(event['method'],event['params'])
                elif kind == 'tool': self.state.set(self.app.tr(tool_status(event.get('name'),event.get('success'))))
                elif kind == 'disconnected':
                    self.busy = False; self.active = False;self.authenticated=False;self.remember_failed_question();self.state.set(event['message']+'；问题已保留，重新连接并登录后可重试。')
                elif kind == 'notice': self.state.set(event['message'])
                elif kind == 'refresh_account': refresh = True
            except Exception as error:
                self.state.set('插件显示失败：'+str(error))
        if getattr(self,'_stream_dirty',False):self._render()
        if refresh:
            if not self.busy and self.client and self.client.connected: self.run(self.client.account,self._account)
            elif self.client and self.client.connected: self.events.put({'kind':'refresh_account','generation':self.generation})
        path = self.app.controller.database
        if path != self.archive_path:
            self.archive_path = path
            if self.client and self.client.thread_id:
                # 切库即撤回旧工具，不把旧会话带入新归档。
                self.client.tools = None
                self.client.close(); self.client = None; self.generation += 1
                self.busy = False;self.authenticated=False; self._clear(); self.account_text.set('归档已切换，请重新连接；登录仍保存在插件目录。')
        try:
            scope = self.current_scope()
            binding=(scope.key,self.app.controller.archive_view_token())
            old_binding=getattr(self,'observed_binding',None)
            if old_binding is not None and old_binding!=binding and self.client:
                self.client.revoke_tools();self.retry_request=None
            self.observed_binding=binding
            if self.scope_labels_key!=binding:
                ids=(scope.user_id,scope.peer_id or scope.user_id)
                self.scope_labels={row['id']:row['nickname'] for row in [*self.app.archive_users,*getattr(self.app,'contact_rows',[])] if row['id'] in ids}
                self.scope_labels_key=binding
            owner=f"{self.scope_labels.get(scope.user_id,'身份')}（#{scope.user_id}）"
            peer=f"{self.scope_labels.get(scope.peer_id,'联系人')}（#{scope.peer_id}）" if scope.peer_id is not None else '全部已归档私聊'
            if self.compact:
                own_name=self.scope_labels.get(scope.user_id,'身份')[:16]
                peer_name=self.scope_labels.get(scope.peer_id,'联系人')[:16] if scope.peer_id is not None else '全部已归档私聊'
                if scope.peer_id is not None:label=f'当前归档 · {own_name} ↔ {peer_name}\n范围：当前会话'
                else:label=f'当前归档 · {own_name} · 全部已归档私聊'
                if self.scope_text.get()!=label:self.scope_text.set(label)
            else:self.scope_text.set(f'已选范围：当前归档 · {owner} ↔ {peer}。只读取查询相关片段。')
            source_changed=self.last_context is not None and self.last_context.source_token!=binding[1]
            if self.client and not self.busy and ((self.client.scope_key is not None and self.client.scope_key!=scope.key) or source_changed):
                self.client.tools=None
                reason='归档原文已变化' if source_changed else '读取范围已切换'
                def cleared(_):self._clear();self.state.set(reason+'，旧对话已清空；可重新提问。')
                self.run(self.client.new_conversation,cleared)
        except Exception as error:
            self.scope_text.set(str(error))
            if self.client and getattr(self,'observed_binding',None) is not None:self.client.revoke_tools()
            self.observed_binding=None
            if self.client and not self.busy and (self.client.scope_key is not None or self.last_context is not None):
                def clear_invalid(_):self._clear();self.state.set('当前无有效会话，旧读取范围已撤销；请选择归档会话。')
                self.run(self.client.new_conversation,clear_invalid)
        self._controls(); self.poll_job = self.root.after(60 if self.busy or self.active else 400,self.poll)

    def close(self):
        if getattr(self,'dialogue_layout_job',None):self.root.after_cancel(self.dialogue_layout_job);self.dialogue_layout_job=None
        self.flush_history()
        if self.config_job:
            self.root.after_cancel(self.config_job);self.flush_configuration()
        parameters=getattr(self,'parameters_popup',None)
        if parameters and parameters.winfo_exists():parameters.destroy()
        popup=getattr(self,'scope_popup',None)
        if popup and popup.winfo_exists():popup.destroy()
        self.closed = True
        if self.reply_job:self.root.after_cancel(self.reply_job)
        if self.follow_job:self.root.after_cancel(self.follow_job)
        self.reply_job=None;self.follow_job=None
        self.root.after_cancel(self.poll_job)
        if self.client: self.client.close()
