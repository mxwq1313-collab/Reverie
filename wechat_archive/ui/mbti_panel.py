"""A top-bar MBTI entry that uses the same login, scope, evidence and history."""
import tkinter as tk
from tkinter import ttk
from ..ai.personality import mbti_prompt


def participants(app, mode):
    owner = next((row for row in app.archive_users if row['id'] == app.owner_id), None)
    if owner is None:
        return []
    rows = [owner]
    if mode == '当前会话':
        peer = next((row for row in app.contact_rows if row['id'] == app.peer_id), None)
        if peer:
            rows.extend(peer.get('members', []) if peer.get('kind') == 'group' else [peer])
    return list({row['id']: row for row in rows if row['id'] > 0}.values())


def open_mbti(app):
    previous = getattr(app, 'mbti_popup', None)
    if previous and previous.winfo_exists():
        previous.lift()
        return previous
    panel = app.agent_panel
    window = tk.Toplevel(app.root)
    app.mbti_popup = window
    window.title(app.tr('MBTI 性格分析'))
    u = app.theme.u
    window.geometry(f'{u(540)}x{u(510)}')
    window.minsize(u(440), u(440))
    window.transient(app.root)
    from .common_widgets import ScrollPanel
    window.columnconfigure(0,weight=1);window.rowconfigure(0,weight=1)
    scroll=ScrollPanel(window,app.theme);scroll.grid(row=0,column=0,sticky='nsew')
    body=scroll.body;body.configure(padding=u(24))
    ttk.Label(body, text='MBTI 性格分析', font=app.theme.title).pack(anchor='w')
    ttk.Label(body, text='从聊天片段，了解表达与沟通倾向', style='Hint.TLabel').pack(anchor='w', pady=(u(6),u(22)))
    from .mbti_resources_panel import open_resources
    ttk.Button(body,text='官方资料与测评',command=lambda:open_resources(app),style='Quiet.TButton').pack(anchor='w',pady=(0,u(16)))
    mode = tk.StringVar(window, value='当前会话')
    target = tk.StringVar(window)
    ttk.Label(body, text='读取范围', font=app.theme.name).pack(anchor='w')
    range_box = ttk.Combobox(body, textvariable=mode, values=('当前会话','当前身份的所有私聊'), state='readonly')
    range_box.pack(fill='x', pady=(u(6),u(16)))
    ttk.Label(body, text='分析对象', font=app.theme.name).pack(anchor='w')
    target_box = ttk.Combobox(body, textvariable=target, state='readonly')
    target_box._raw_values = True
    target_box.pack(fill='x', pady=(u(6),u(10)))
    context = tk.StringVar(window)
    ttk.Label(body, textvariable=context, style='Hint.TLabel', wraplength=u(480)).pack(anchor='w')
    ttk.Separator(body).pack(fill='x', pady=u(18))
    ttk.Label(body, text='结合原文引用分析四个维度，给出倾向、反向证据和待验证问题。证据不足的维度会保留为未定。', wraplength=u(480)).pack(anchor='w')
    ttk.Label(body, text='所选范围的相关文字会发送给 OpenAI；结果保存在本机 Codex 历史中。', style='Hint.TLabel', wraplength=u(480)).pack(anchor='w', pady=(u(10),u(12)))
    hint = tk.StringVar(window)
    ttk.Label(body, textvariable=hint, style='Hint.TLabel', wraplength=u(480)).pack(anchor='w')
    footer = ttk.Frame(window,padding=(u(24),u(12),u(24),u(18)))
    footer.grid(row=1,column=0,sticky='ew')
    choices = {}
    binding = (app.controller.database, app.owner_id, app.peer_id)
    filter_binding = getattr(app, 'loaded_query', None)
    archive_token = app.controller.archive_view_token() if app.controller.database else None

    def refresh(*_):
        nonlocal choices
        choices = {f"{row['nickname']} · #{row['id']}": row for row in participants(app, mode.get())}
        target_box.configure(values=tuple(choices))
        if target.get() not in choices:
            target.set(next(iter(choices), ''))
        peer = next((row['nickname'] for row in app.contact_rows if row['id'] == app.peer_id), '未选择会话')
        query = getattr(app, 'loaded_query', None)
        filters = ''
        if query and query[0] == app.owner_id:
            filters = (' · 关键词：'+query[2] if query[2] else '') + (' · '+(query[3] or '开始')+' 至 '+(query[4] or '现在') if query[3] or query[4] else '')
        context.set((app.controller.database.name+' · ' if app.controller.database else '') + (peer if mode.get() == '当前会话' else '当前身份的全部已归档私聊') + filters)
        free = not (app.busy or panel.busy or panel.active)
        ready = bool(panel.client and panel.client.connected and panel.authenticated)
        start.configure(state='normal' if choices and free and ready and app.controller.database and (mode.get() != '当前会话' or app.peer_id is not None) else 'disabled')
        hint.set('请先打开归档并选择会话。' if not choices else '请等待当前操作完成。' if not free else '先在设置中连接 Codex 并登录 ChatGPT。' if not ready else '使用当前 Codex 模型与努力程度；点击后开启一段独立分析。')

    def analyze():
        current = (app.controller.database, app.owner_id, app.peer_id)
        if current != binding or archive_token != app.controller.archive_view_token() or filter_binding != getattr(app, 'loaded_query', None):
            hint.set('归档或会话已变化，请关闭后重新打开 MBTI。')
            start.configure(state='disabled')
            return
        if app.busy or panel.busy or panel.active:
            refresh()
            return
        row = choices.get(target.get())
        if row is None or row['id'] not in {x['id'] for x in participants(app,mode.get())}:
            hint.set('请重新选择分析对象。')
            return
        if not panel.client or not panel.client.connected or not panel.authenticated:
            refresh()
            return
        try:
            from ..ai.mbti_resources import resource_context
            resources=resource_context(app.controller.profile_dir,app.controller.settings().get('ai',{}).get('mbti_bank_id'))
            task=mbti_prompt(row['id'],row['nickname'],context.get(),resources)
        except Exception as error:
            hint.set('分析资源未就绪：'+str(error));return
        panel.scope.set(mode.get())
        app.notify_copilot_binding()
        panel.new_conversation()
        panel.fill_prompt('分析 '+row['nickname']+' 的 MBTI 性格倾向\n范围：'+context.get())
        app.open_copilot()
        panel.send(task_text=task)
        if panel.active:
            window.destroy()
        else:
            hint.set(panel.state.get())

    ttk.Button(footer, text='连接与登录', command=lambda:(window.destroy(),app.show_page('AI设置'))).pack(side='left')
    start = ttk.Button(footer, text='由 Codex 分析', command=analyze, style='Primary.TButton')
    start.pack(side='right')
    range_box.bind('<<ComboboxSelected>>', refresh)
    target_box.bind('<<ComboboxSelected>>', refresh)
    window.bind('<Escape>', lambda _:window.destroy())
    window.mbti_mode = mode
    window.mbti_target = target
    window.mbti_start = start
    window.mbti_hint = hint
    window.mbti_refresh = refresh
    refresh()
    app.theme.apply_tree(window)
    app.localizer.apply(window, ())
    window.update_idletasks()
    x=app.root.winfo_rootx()+(app.root.winfo_width()-window.winfo_width())//2
    y=app.root.winfo_rooty()+(app.root.winfo_height()-window.winfo_height())//2
    window.geometry(f'+{max(0,min(x,window.winfo_screenwidth()-window.winfo_width()))}+{max(0,min(y,window.winfo_screenheight()-window.winfo_height()-40))}')
    return window
