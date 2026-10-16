"""Codex conversation surface; connection setup stays in Settings."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .common_widgets import Collapsible
from .theme import ACCENT,SECONDARY,PAPER
from .rounded import RoundedSurface
from .model_controls import AUTO_MODEL

def build_configuration(panel):
    app=panel.app;root=panel.root;u=app.theme.u;page=app.settings_ai_codex
    saved=app.controller.settings().get('ai',{});saved=saved if isinstance(saved,dict) else {}
    ttk.Label(page,text='Codex',font=app.theme.name).pack(anchor='w',pady=(0,u(10)))
    row=ttk.Frame(page);row.pack(fill='x')
    for attr,label,command in (('connect_button','连接 Codex',panel.connect),('login_button','登录 ChatGPT',panel.login),('account_button','检查登录',panel.refresh_account),('cancel_login_button','取消登录',panel.cancel_login),('logout_button','退出登录',panel.logout)):
        button=ttk.Button(row,text=label,command=command);button.pack(side='left',padx=(0,u(6)));setattr(panel,attr,button)
    panel.account_text=tk.StringVar(root,value='未连接 · 独立登录状态')
    ttk.Label(page,textvariable=panel.account_text,style='Hint.TLabel',wraplength=u(720)).pack(fill='x',pady=u(8))
    panel.binary=tk.StringVar(root)
    from ..agent.client import find_codex,bundled_codex
    from pathlib import Path
    bundled=bundled_codex();selected=saved.get('codex_executable');panel.runtime_revision=saved.get('runtime_revision')
    if bundled and (saved.get('runtime_revision')!='0.162.1' or not selected or not Path(selected).is_file()):selected=str(bundled);panel.runtime_revision='0.162.1'
    try:panel.binary.set(selected or str(find_codex()))
    except Exception:panel.binary.set(saved.get('codex_executable',''))
    panel.advanced=Collapsible(page,'运行组件',app.theme);panel.advanced.pack(fill='x')
    row=ttk.Frame(panel.advanced.content);row.pack(fill='x',pady=u(6))
    ttk.Entry(row,textvariable=panel.binary,state='readonly').pack(side='left',fill='x',expand=True)
    panel.pick_button=app.icon(row,'folder','选择 codex.exe',panel.pick_binary);panel.pick_button.pack(side='left',padx=u(6))
    panel.connection_options=panel.advanced;panel.more=panel.advanced
    panel.scope=tk.StringVar(root,value=saved.get('scope') if saved.get('scope') in ('当前会话','当前身份的所有私聊') else '当前会话')
    model_name=saved.get('model');model_id=saved.get('model_id')
    cached=isinstance(model_name,str) and isinstance(model_id,str) and bool(model_id)
    if cached:panel.model_ids[model_name]=model_id
    panel.model=tk.StringVar(root,value=model_name if cached else AUTO_MODEL);panel.steps=tk.StringVar(root)

def build_compact(panel,page):
    app=panel.app;root=panel.root;u=app.theme.u
    app.theme.style.configure('Copilot.TButton',font=app.theme.small,padding=(u(5),u(4)),borderwidth=0)
    page.columnconfigure(0,weight=1);page.rowconfigure(2,weight=1);build_configuration(panel)
    panel.scope_text=tk.StringVar(root,value='选择归档范围');panel.scope_summary=tk.StringVar(root)
    def scope_display(*_):
        owner=next((x['nickname'] for x in app.archive_users if x['id']==app.owner_id),'选择身份')
        peer=next((x['nickname'] for x in getattr(app,'contact_rows',[]) if x['id']==app.peer_id),'选择会话')
        value=owner+'  ›  '+(peer if panel.scope.get()=='当前会话' else '全部私聊') if app.controller.database else '选择归档会话'
        value=app.theme.elide(value,max(u(120),page.winfo_width()-u(44)),True)
        if panel.scope_summary.get()!=value:panel.scope_summary.set(value)
    panel.scope_text.trace_add('write',scope_display);scope_display()
    page.bind('<Configure>',lambda event:scope_display() if event.widget is page else None,add='+')
    app.theme.style.configure('Scope.Copilot.TButton',anchor='w')
    scope_row=ttk.Frame(page);scope_row.grid(row=0,column=0,sticky='ew',pady=(u(5),u(7)));scope_row.columnconfigure(0,weight=1)
    panel.scope_button=ttk.Button(scope_row,textvariable=panel.scope_summary,command=panel.scope_picker,style='Scope.Copilot.TButton',cursor='hand2');panel.scope_button.configure(width=1);panel.scope_button.grid(row=0,column=0,sticky='ew');panel.scope_button._raw_text=True
    panel.scope_box=ttk.Combobox(scope_row,textvariable=panel.scope,values=('当前会话','当前身份的所有私聊'),state='readonly',width=9,style='Copilot.TCombobox');panel.scope_box.grid_remove()
    row=ttk.Frame(page);row.grid(row=1,column=0,sticky='ew',pady=(0,u(7)))
    for attr,icon,label,command in (('new_button','new','新对话',panel.new_conversation),('history_button','history','历史对话',panel.show_history),('copy_button','copy','复制回答',panel.copy_answer),('export_button','save','保存对话',panel.export_conversation),('settings_button','settings','设置',lambda:app.show_page('AI设置'))):
        button=app.icon(row,icon,label,command,'Copilot.TButton');button.pack(side='right' if attr=='settings_button' else 'left');setattr(panel,attr,button)
    panel.transcript=ScrolledText(page,height=6,width=1,wrap='word',font=app.theme.body,state='disabled');app.theme.text_surface(panel.transcript);panel.transcript.grid(row=2,column=0,sticky='nsew')
    panel.transcript.tag_configure('role',foreground=ACCENT,font=app.theme.name,spacing1=u(16),spacing3=u(7));panel.transcript.tag_configure('system',foreground=SECONDARY)
    panel.empty_notice=ttk.Frame(panel.transcript.frame)
    ttk.Label(panel.empty_notice,text='从归档开始提问',font=app.theme.name).pack(pady=(0,u(8)))
    panel.start_button=ttk.Button(panel.empty_notice,text='连接 Codex',command=panel.start_action,style='Copilot.TButton');panel.start_button.pack()
    panel.latest_button=app.icon(panel.transcript.frame,'latest','回到最新',panel.jump_latest,'Copilot.TButton')
    panel.transcript.configure(yscrollcommand=panel.transcript_scrolled)
    surface=RoundedSurface(page,app.theme,app.theme.palette['AI'],PAPER,radius=12,padding=10);surface._ai_composer=True
    surface.grid(row=4,column=0,sticky='ew',pady=(u(7),u(5)));composer=surface.content;panel.composer_surface=surface
    panel.input=ScrolledText(composer,height=3,width=1,wrap='word',font=app.theme.body);panel.input.pack(fill='x');app.theme.text_surface(panel.input,editable=True)
    panel.input.bind('<Control-Return>',panel.send_shortcut);panel.input.bind('<<Modified>>',panel.input_changed);panel.input.bind('<Escape>',panel.leave_input)
    row=ttk.Frame(composer);row.pack(fill='x',pady=(u(5),0));panel.send_row=row
    panel.send_button=app.icon(row,'send','发送',panel.send);panel.send_button.pack(side='right');panel.stop_button=app.icon(row,'stop','停止回答',panel.stop)
    from .parameter_picker import build_parameters
    build_parameters(panel,page)
    recovery=ttk.Frame(page);recovery.grid(row=6,column=0,sticky='ew')
    panel.retry_button=app.icon(recovery,'retry','重试问题',panel.retry_question,'Copilot.TButton');panel.retry_button.pack(side='left')
    panel.edit_question_button=app.icon(recovery,'edit','取回编辑',panel.edit_failed_question,'Copilot.TButton');panel.edit_question_button.pack(side='left');recovery.grid_remove();panel.recovery_row=recovery
    panel.state=tk.StringVar(root);panel.gate_hint=tk.StringVar(root);panel.compact_hint=tk.StringVar(root)
    hint=ttk.Label(page,textvariable=panel.compact_hint,style='Hint.TLabel',wraplength=u(300));hint.grid(row=7,column=0,sticky='ew',pady=u(4))
    def update_hint(*_):
        value=panel.state.get() if panel.busy or panel.active or any(word in panel.state.get() for word in ('失败','未完成','已停止','变化','撤销')) else ''
        value=value[:100]+('…' if len(value)>100 else '')
        if panel.compact_hint.get()!=value:panel.compact_hint.set(value)
        if value and not hint.winfo_manager():hint.grid(row=7,column=0,sticky='ew',pady=u(4))
        elif not value and hint.winfo_manager():hint.grid_remove()
        if panel.retry_request and not recovery.winfo_manager():recovery.grid()
        elif not panel.retry_request and recovery.winfo_manager():recovery.grid_remove()
    panel.state.trace_add('write',update_hint);panel.gate_hint.trace_add('write',update_hint)
    page.bind('<Configure>',lambda event:hint.configure(wraplength=max(u(160),event.width-u(20))) if event.widget is page else None,add='+');update_hint()
