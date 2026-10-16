"""添加、导出和工具页；低频参数折叠，结果先显示真实计数。"""
import tkinter as tk
from tkinter import ttk
from .. import __version__
from .common_widgets import Collapsible,ResultCard,ScrollPanel
from .import_controller import FORMAT_LABELS
from .agent_panel import AgentPanel
from .knowledge_panel import KnowledgePanel
from .search_entry import SearchEntry
from .source_options import SOURCE_RANGES


class OperationPanels:
    def notebook_page(self,notebook,name,label=None):
        if name=='文字小工坊':
            frame=ttk.Frame(notebook,padding=self.theme.u(20));frame._lazy_theme=True;notebook.add(frame,text=label or name)
            self.pages[name]=frame;self.tab_routes[name]=(notebook,frame);return frame
        scroll=ScrollPanel(notebook,self.theme);scroll._lazy_theme=True;notebook.add(scroll,text=label or name)
        self.pages[name]=scroll.body;self.tab_routes[name]=(notebook,scroll)
        return scroll.body

    def build_add(self):
        page=self.pages['添加记录'];self.title(page,'添加聊天记录')
        self.add_notebook=ttk.Notebook(page);self.add_notebook.pack(fill='both',expand=True,pady=(self.theme.u(10),0))
        self.notebook_page(self.add_notebook,'电脑微信','从电脑微信读取')
        self.notebook_page(self.add_notebook,'导入文件','导入已有文件')
        self.build_source();self.build_import()

    def flow_heading(self,parent,number,label):
        u=self.theme.u;row=ttk.Frame(parent);row.pack(fill='x',pady=(u(10),u(8)))
        marker=tk.Canvas(row,width=u(26),height=u(26),background=self.theme.palette['PAPER'],highlightthickness=0)
        marker.create_oval(u(2),u(2),u(24),u(24),fill=self.theme.palette['SELECTED'],outline='')
        marker.create_text(u(13),u(13),text=str(number),font=self.theme.small,fill=self.theme.palette['ACCENT']);marker.pack(side='left',padx=(0,u(9)))
        ttk.Label(row,text=label,font=self.theme.name).pack(side='left')

    def build_source(self):
        page=self.pages['电脑微信'];u=self.theme.u
        self.source_step=tk.StringVar(self.root,value='1 · 检测账号');self.flow_heading(page,1,'选择账号')
        row=ttk.Frame(page);row.pack(fill='x',pady=u(4))
        self.account_var=tk.StringVar(self.root);self.account_box=ttk.Combobox(row,textvariable=self.account_var,state='readonly',width=24);self.account_box.pack(side='left',fill='x',expand=True)
        self.account_box.bind('<<ComboboxSelected>>',lambda _:self.source_account_changed())
        self.detect_button=self.button(row,'检测账号',self.detect_source);self.detect_button.pack(side='left',padx=(u(8),0))
        self.source_info=tk.StringVar(self.root,value='检测已登录的电脑微信账号')
        ttk.Label(page,textvariable=self.source_info,style='Hint.TLabel',wraplength=u(680)).pack(anchor='w',pady=u(5))
        self.flow_heading(page,2,'选择会话')
        row=ttk.Frame(page);row.pack(fill='x',pady=u(4));self.source_keyword=tk.StringVar(self.root)
        entry=SearchEntry(row,self.theme,self.source_keyword,'搜索联系人或群聊…',self.load_source_contacts);self.source_contact_entry=entry;entry.pack(side='left',fill='x',expand=True)
        self.load_source_button=self.icon(row,'contacts','连接并加载联系人',self.load_source_contacts);self.load_source_button.pack(side='left',padx=u(4))
        self.icon(row,'search','搜索联系人',self.load_source_contacts).pack(side='left')
        self.source_contact_host=ttk.Frame(page,height=u(65));self.source_contact_host.pack(fill='x',pady=u(6));self.source_contact_host.pack_propagate(False)
        self.source_tree=self.tree(self.source_contact_host,('消息数','本人 / 成员占比'),(85,230),height=4)
        self.source_tree.configure(show='tree headings');self.source_tree.heading('#0',text='会话 / 群成员');self.source_tree.column('#0',width=u(220),minwidth=u(130));self.source_tree.column('本人 / 成员占比',minwidth=u(190))
        self.source_tree.master.pack_forget()
        self.source_empty=ttk.Label(self.source_contact_host,text='加载联系人后选择会话',style='Hint.TLabel');self.source_empty.place(relx=.5,rely=.5,anchor='center')
        self.flow_heading(page,3,'归档')
        row=ttk.Frame(page);row.pack(fill='x',pady=u(6));self.source_scope=tk.StringVar(self.root,value='全部电脑本地记录')
        self.source_scope_box=ttk.Combobox(row,textvariable=self.source_scope,values=tuple(SOURCE_RANGES),state='readonly',width=22);self.source_scope_box.pack(side='left')
        self.acquire_button=self.button(row,'一键读取（含图片/表情）',self.acquire_source,True);self.acquire_button.pack(side='left',padx=u(10))
        self.source_upgrade_button=self.button(row,'导入副本文件',self.import_copy_file);self.source_upgrade_button.pack(side='left',padx=u(6))
        self.source_capability_short=tk.StringVar(self.root);ttk.Label(page,textvariable=self.source_capability_short,style='Hint.TLabel')
        self.source_advanced=Collapsible(page,'高级设置',self.theme);self.source_advanced.pack(fill='x',pady=u(6))
        self.source_allow_cdn=tk.BooleanVar(self.root,value=self.controller.settings().get('source_media',{}).get('allow_cdn',True))
        self.source_cdn_toggle=ttk.Checkbutton(self.source_advanced.content,text='从微信官方CDN补全缺失表情（不发送聊天正文）',variable=self.source_allow_cdn);self.source_cdn_toggle.pack(anchor='w',pady=u(6))
        ttk.Label(self.source_advanced.content,text='全部记录按批次归档，可取消；重复读取会去重并补充附件。',style='Hint.TLabel',wraplength=u(640)).pack(anchor='w',pady=u(4))
        self.repair_emoji_button=self.button(self.source_advanced.content,'补全已归档表情',self.repair_archived_emojis);self.repair_emoji_button.pack(anchor='w',pady=u(6))
        def save_media_policy(*_):
            settings=self.controller.settings();settings['source_media']={'allow_cdn':self.source_allow_cdn.get()};self.controller.save_settings(settings)
        self.source_allow_cdn.trace_add('write',save_media_policy)
        self.source_root=tk.StringVar(self.root);row,_=self.entry_row(self.source_advanced.content,'微信数据目录',self.source_root)
        self.icon(row,'folder','选择目录',self.choose_source_root).pack(side='left',padx=u(6))
        self.source_capability_text=tk.StringVar(self.root)
        ttk.Label(self.source_advanced.content,textvariable=self.source_capability_text,style='Hint.TLabel',wraplength=u(680))
        self.update_source_capabilities()
        self.source_cards=ResultCard(page,self.theme);self.source_result=self.source_cards.details
        self.icon(self.source_cards,'chat','查看聊天归档',lambda:self.show_page('聊天归档')).pack(anchor='e')

    def refresh_source_selection(self):
        if self.source_tree.get_children():
            self.source_empty.place_forget();self.source_contact_host.configure(height=self.theme.u(230));self.source_tree.master.pack(fill='both',expand=True)
        else:
            self.source_tree.master.pack_forget();self.source_contact_host.configure(height=self.theme.u(65));self.source_empty.place(relx=.5,rely=.5,anchor='center')

    def build_import(self):
        page=self.pages['导入文件'];u=self.theme.u
        self.import_step=tk.StringVar(self.root,value='1 · 选择文件或目录');self.flow_heading(page,1,'选择来源')
        self.import_source=tk.StringVar(self.root);row,_=self.entry_row(page,'文件 / 目录',self.import_source)
        self.icon(row,'file','选择文件',self.pick_import_file).pack(side='left',padx=u(5));self.icon(row,'folder','选择目录',self.pick_import_folder).pack(side='left')
        self.flow_heading(page,2,'预览并导入')
        row=ttk.Frame(page);row.pack(fill='x',pady=u(6));self.preview_button=self.button(row,'预览检查',lambda:self.import_action(True));self.preview_button.pack(side='left')
        self.import_button=self.button(row,'开始导入',lambda:self.import_action(False),True);self.import_button.pack(side='left',padx=u(10))
        self.import_advanced=Collapsible(page,'高级设置',self.theme);self.import_advanced.pack(fill='x',pady=u(12));options=self.import_advanced.content
        row=ttk.Frame(options);row.pack(fill='x',pady=u(7));ttk.Label(row,text='数据类型',width=12).pack(side='left')
        self.import_kind=tk.StringVar(self.root,value=FORMAT_LABELS['auto']);ttk.Combobox(row,textvariable=self.import_kind,values=[FORMAT_LABELS[key] for key in ('auto','json','csv','rich','rich_snapshot','android','external','snapshot')],state='readonly',width=28).pack(side='left')
        self.import_strict=tk.BooleanVar(self.root,value=False);ttk.Checkbutton(options,text='严格模式：出现失败记录时整批拒绝',variable=self.import_strict).pack(anchor='w',pady=u(5))
        self.csv_frame=ttk.Frame(options);self.csv_namespace=tk.StringVar(self.root,value='default');self.csv_zone=tk.StringVar(self.root,value='+08:00')
        self.entry_row(self.csv_frame,'CSV 账号标签',self.csv_namespace);self.entry_row(self.csv_frame,'CSV 默认时区',self.csv_zone)
        self.import_kind.trace_add('write',lambda *_:self.update_csv_options());self.import_source.trace_add('write',lambda *_:self.update_csv_options())
        self.import_cards=ResultCard(page,self.theme);self.import_result=self.import_cards.details
        self.icon(self.import_cards,'chat','查看聊天归档',lambda:self.show_page('聊天归档')).pack(anchor='e');self.update_csv_options()

    def update_source_capabilities(self):
        if not hasattr(self,'source_capability_text'):return
        try:capability=self.controller.source_capabilities()
        except Exception as error:
            capability={'can_upgrade':False,'description':'读取能力未确认：'+str(error)}
        self.source_capability_text.set(capability['description'])
        self.source_upgrade_button.configure(state='normal' if not self.busy else 'disabled')
        if hasattr(self,'source_capability_short'):
            self.source_capability_short.set('未选择归档' if not self.controller.database else '基础归档 · 单次≤100000条 / 64 MiB' if capability['can_upgrade'] else '扩展归档 · 全量分批读取')

    def update_csv_options(self):
        csv=self.import_kind.get()==FORMAT_LABELS.get('csv') or self.import_kind.get()==FORMAT_LABELS['auto'] and self.import_source.get().lower().endswith('.csv')
        if csv:self.csv_frame.pack(fill='x',pady=self.theme.u(5))
        else:self.csv_frame.pack_forget()
        self.csv_options_visible=csv

    def build_export(self):
        page=self.pages['导出归档'];self.title(page,'导出聊天归档','导出所选范围内全部消息及可用附件，不受当前加载页或搜索筛选影响。')
        u=self.theme.u
        body=ScrollPanel(page,self.theme);body.pack(fill='both',expand=True);content=body.body
        self.export_caption=tk.StringVar(self.root,value='请先打开归档')
        ttk.Label(content,textvariable=self.export_caption,font=self.theme.name,wraplength=u(780)).pack(anchor='w',pady=(0,u(15)))
        row=ttk.Frame(content);row.pack(fill='x',pady=u(8));ttk.Label(row,text='导出范围',width=12).pack(side='left')
        self.export_scope=tk.StringVar(self.root,value='全部已归档内容');ttk.Combobox(row,textvariable=self.export_scope,values=('全部已归档内容','当前查看身份','当前会话'),state='readonly',width=27).pack(side='left')
        self.export_scope.trace_add('write',lambda *_:self.update_export_caption())
        row=ttk.Frame(content);row.pack(fill='x',pady=u(8));ttk.Label(row,text='文件格式',width=12).pack(side='left')
        self.export_format=tk.StringVar(self.root,value=self.ui_settings['export_format']);ttk.Combobox(row,textvariable=self.export_format,values=('HTML 和 TXT','仅 HTML','仅 TXT'),state='readonly',width=27).pack(side='left')
        self.export_parent=tk.StringVar(self.root,value=self.default_export_path());row,_=self.entry_row(content,'保存位置',self.export_parent);self.button(row,'选择位置',self.pick_export_parent).pack(side='left',padx=u(8))
        self.export_zone=tk.StringVar(self.root,value='+08:00');self.entry_row(content,'显示时区',self.export_zone)
        self.export_button=self.button(content,'导出可读文件',self.export_action,True);self.export_button.pack(anchor='w',pady=u(14))
        self.export_result=self.text_panel(content,height=8)
        self.last_export=None
        row=ttk.Frame(content);row.pack(fill='x',pady=u(6))
        self.open_export_button=self.button(row,'打开阅读首页',lambda:self.open_export_result(False));self.open_export_button.pack(side='left')
        self.open_export_folder_button=self.button(row,'打开文件夹',lambda:self.open_export_result(True));self.open_export_folder_button.pack(side='left',padx=u(6))
        self.copy_export_path_button=self.button(row,'复制路径',self.copy_export_path);self.copy_export_path_button.pack(side='left')
        self.update_export_actions()

    def update_export_caption(self):
        if not hasattr(self,'export_caption'):return
        if not self.controller.database:self.export_caption.set('请先打开归档');return
        scope=self.export_scope.get();names={row['id']:row['nickname'] for row in self.archive_users};names.update({row['id']:row['nickname'] for row in getattr(self,'contact_rows',[])})
        if scope in ('全部已归档文本','全部已归档内容'):value=self.controller.database.name+' · 全部已归档内容'
        elif scope=='当前查看身份':value='查看身份：'+names.get(self.owner_id,'尚未选择')+' · 全部已归档会话'
        else:value=names.get(self.owner_id,'尚未选择')+' ↔ '+names.get(self.peer_id,'尚未选择')+' · 当前会话全部内容'
        self.export_caption.set(value)

    def prepare_export(self,scope):
        if scope=='当前会话' and (self.owner_id is None or self.peer_id is None):self.status.set('先选择一个已归档会话。');return
        self.export_scope.set(scope);self.update_export_caption();self.show_page('导出归档')

    def build_tools(self):
        page=self.pages['工具与设置'];self.title(page,'工具')
        self.tools_notebook=ttk.Notebook(page);self.tools_notebook.pack(fill='both',expand=True,pady=(self.theme.u(10),0))
        for name,label in (('数据管理','归档管理'),('本地知识问答','语义检索'),('文字小工坊','文字小工坊')):
            self.notebook_page(self.tools_notebook,name,label)
        self.pages['备份检查']=self.pages['数据管理']
        self.build_management();self.build_user_settings();self.build_reports()
        capsule=ttk.Frame(self.page_host,padding=self.theme.u(16));capsule._lazy_theme=True
        capsule.grid(row=0,column=0,sticky='nsew');capsule.grid_remove();self.pages['时光胶囊']=capsule
        scroll=ScrollPanel(capsule,self.theme);scroll.pack(fill='both',expand=True);self.capsule_content=scroll.body
        from .memory_popup import MemoryPopup
        self.memory_popup=MemoryPopup(self);self.memory_content=self.memory_popup.content
        from .toolbox_panel import ToolboxPanel
        self.toolbox_panel=ToolboxPanel(self)
        self.tools_notebook.bind('<<NotebookTabChanged>>',self.tool_tab_changed,add='+')
        self.tools_notebook.bind('<Configure>',lambda _:self.fit_tool_tabs(),add='+')
        self.agent_panel=AgentPanel(self,self.copilot_body,compact=True)
        self.knowledge_panel=KnowledgePanel(self,self.pages['本地知识问答'])

    def fit_tool_tabs(self):
        if self.closed:return
        names=('数据管理','本地知识问答','文字小工坊')
        labels=('归档管理','语义检索','文字小工坊')
        width=self.tools_notebook.winfo_width()
        if width<20:return
        key=(width,self.theme.generation,self.localizer.language)
        if key==getattr(self,'tool_tab_size_key',None):return
        self.tool_tab_size_key=key
        full=[self.tr(label) for label in labels]
        compact=sum(self.theme.font.measure(label)+self.theme.u(28) for label in full)>width
        short=('Archive','Search','Text') if self.localizer.language=='en_US' else ('管理','检索','文字工坊')
        for name,label in zip(names,short if compact else full):self.tools_notebook.tab(self.tab_routes[name][1],text=label)

    def tool_tab_changed(self,event=None):
        if self.closed:return
        selected=self.tools_notebook.select()
        name=next((key for key,(notebook,tab) in self.tab_routes.items() if notebook is self.tools_notebook and str(tab)==selected),None)
        if name and getattr(self,'current_page',None)=='工具与设置':
            self.current_subpage=name
            self.toolbox_panel.activate(name)

    def build_management(self):
        from .workspace_widgets import card,ActionRow
        page=self.pages['数据管理'];u=self.theme.u
        workspace=card(page,self.theme,'归档工作区','选择归档，整理联系人与文本消息。当前会话沿用聊天归档中的选择。')
        ttk.Label(workspace,textvariable=self.archive_label,font=self.theme.name).pack(anchor='w',pady=(0,u(4)))
        ttk.Label(workspace,textvariable=self.summary,style='Hint.TLabel').pack(anchor='w',pady=(0,u(10)))
        actions=ActionRow(workspace,self.theme)
        for label,command,primary in (('打开归档',self.open_archive,True),('新建归档',self.new_archive,False),('数据文件夹',self.open_data_folder,False)):
            actions.add(self.button(actions,label,command,primary))
        contacts=card(page,self.theme,'联系人','有消息关联的联系人会受到保护；编辑前先选择对应条目。')
        actions=ActionRow(contacts,self.theme)
        for label,command in (('新增联系人',lambda:self.user_editor()),('编辑联系人',lambda:self.user_editor(True)),('删除联系人',self.delete_user),('刷新列表',self.refresh_archive)):
            actions.add(self.button(actions,label,command))
        self.user_tree=self.tree(contacts,('ID','昵称','来源标识'),(54,210,330),height=4)
        self.user_tree.bind('<Double-1>',lambda _:self.user_editor(True))
        messages=card(page,self.theme,'当前会话内容','双击查看消息；私聊文本可编辑，群聊、图片和附件保留原有结构。')
        actions=ActionRow(messages,self.theme)
        for label,command in (('新增文本消息',lambda:self.message_editor()),('编辑选中消息',lambda:self.message_editor(True)),('删除选中消息',self.delete_message),('加载当前会话',lambda:self.load_messages())):
            actions.add(self.button(actions,label,command))
        self.message_tree=self.tree(messages,('ID','时间','发送者','接收者','内容'),(48,150,100,100,260),height=6)
        self.message_tree.bind('<Double-1>',lambda _:self.message_editor(True))

    def build_backup(self):
        page=self.pages['备份检查'];u=self.theme.u
        ttk.Label(page,text='保留原有结构、文件头与有限载荷检查；官方备份正文未解密时不能导入。',style='Hint.TLabel',wraplength=u(800)).pack(anchor='w',pady=(0,u(12)))
        self.backup_source=tk.StringVar(self.root);row,_=self.entry_row(page,'备份目录',self.backup_source);self.button(row,'选择目录',self.pick_backup).pack(side='left',padx=u(7))
        row=ttk.Frame(page);row.pack(fill='x',pady=u(12))
        for label,action in (('结构检查','inspect'),('分析 RMFH 文件头','analyze'),('探测有限载荷','study')):self.button(row,label,lambda value=action:self.backup_action(value)).pack(side='left',padx=(0,u(8)))
        self.backup_result=self.text_panel(page,height=14)

    def build_reports(self):
        page=self.pages['报告与设置'];u=self.theme.u
        row=ttk.Frame(page);row.pack(fill='x');self.button(row,'刷新报告',self.refresh_reports).pack(side='left')
        self.report_tree=self.tree(page,('报告文件','修改时间'),(530,190),height=6);self.report_tree.bind('<<TreeviewSelect>>',self.select_report)
        self.report_paths={};self.report_text=self.text_panel(page,height=13)

    def build_settings(self):
        page=self.pages['归档与界面'];u=self.theme.u
        self.archive_settings=tk.StringVar(self.root)
        ttk.Label(page,textvariable=self.archive_settings,wraplength=u(780)).pack(anchor='w',pady=(0,u(18)))
        row=ttk.Frame(page);row.pack(fill='x')
        for label,command in (('新建归档',self.new_archive),('打开归档',self.open_archive),('恢复最近归档',self.restore_recent),('打开数据文件夹',self.open_data_folder)):
            self.button(row,label,command).pack(side='left',padx=(0,u(7)))
        row=ttk.Frame(page);row.pack(fill='x',pady=(u(12),0))
        self.upgrade_button=self.button(row,'创建升级副本',self.upgrade_archive_copy,True);self.upgrade_button.pack(side='left')
        ttk.Label(row,text='保留原库，选择一个新文件；旧版软件不能打开升级副本。',style='Hint.TLabel',wraplength=u(470)).pack(side='left',padx=u(12))
        ttk.Separator(page).pack(fill='x',pady=u(22))
        row=ttk.Frame(page);row.pack(fill='x',pady=u(7));ttk.Label(row,text='聊天正文字号',width=14).pack(side='left')
        self.text_size=tk.IntVar(self.root,value=self.theme.text_size);ttk.Combobox(row,textvariable=self.text_size,values=(14,15,16,17,18),state='readonly',width=8).pack(side='left')
        ttk.Label(row,text='逻辑像素 · 根据系统 DPI 缩放',style='Hint.TLabel').pack(side='left',padx=u(10))
        self.compact_nav=tk.BooleanVar(self.root,value=self.controller.preferences()['compact_nav'])
        ttk.Checkbutton(page,text='使用紧凑导航',variable=self.compact_nav).pack(anchor='w',pady=u(8))
        self.button(page,'应用阅读设置',self.apply_reading_settings).pack(anchor='w',pady=u(8))
        ttk.Label(page,text='思绪1.1支持群聊、表情与附件；未知格式和未取得的原文件会明确标注。旧归档请先创建升级副本。',style='Hint.TLabel',wraplength=u(780)).pack(anchor='w',pady=u(20))
        self.update_archive_settings()

    def update_archive_settings(self):
        if hasattr(self,'archive_settings'):
            self.archive_settings.set(f"版本 {__version__}\n当前归档：{self.controller.database or '尚未打开'}\n数据与报告目录：{self.controller.data_dir}")

    def apply_reading_settings(self):
        self.apply_user_settings()
