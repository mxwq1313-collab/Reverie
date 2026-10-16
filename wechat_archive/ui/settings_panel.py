"""User settings and AI configuration, separate from the reading workspace."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from ..branding import window_title
from .theme import CANVAS

THEMES={'浅色':'light','深色':'dark','跟随系统':'system','暖砂':'sand','雾蓝':'blue','松绿':'green','紫雾':'violet'}
LANGUAGES={'简体中文':'zh_CN','English':'en_US'}


class SettingsMixin:
    def build_user_settings(self):
        page=self.pages['设置'];u=self.theme.u
        self.title(page,'用户设置')
        self.settings_notebook=ttk.Notebook(page);self.settings_notebook.pack(fill='both',expand=True,pady=u(10))
        appearance=self.notebook_page(self.settings_notebook,'归档与界面','外观')
        storage=self.notebook_page(self.settings_notebook,'存储设置','存储')
        ai=self.notebook_page(self.settings_notebook,'AI设置','AI设置')
        self.notebook_page(self.settings_notebook,'报告与设置','导入与分析报告')
        self.pages['Codex 助手']=ai;self.tab_routes['Codex 助手']=self.tab_routes['AI设置']
        prefs=self.controller.user_preferences()
        self.theme_choice=tk.StringVar(self.root,value=next(name for name,value in THEMES.items() if value==prefs['theme']))
        self.font_family=tk.StringVar(self.root,value=prefs['font_family'] or '系统推荐')
        self.text_size=tk.IntVar(self.root,value=prefs['text_size'])
        self.language_choice=tk.StringVar(self.root,value=next(name for name,value in LANGUAGES.items() if value==prefs['language']))
        self.wheel_speed=tk.IntVar(self.root,value=prefs['wheel_speed'])
        for label,var,values in (('界面主题',self.theme_choice,tuple(THEMES)),('界面字体',self.font_family,('系统推荐',*self.theme.available_fonts)),
                                 ('正文字号',self.text_size,tuple(range(12,25))),('界面语言',self.language_choice,tuple(LANGUAGES)),
                                 ('滚动速度',self.wheel_speed,(24,36,48,60,72,96,120))):
            row=ttk.Frame(appearance);row.pack(fill='x',pady=u(8));ttk.Label(row,text=label,width=16).pack(side='left')
            ttk.Combobox(row,textvariable=var,values=values,state='readonly',width=30).pack(side='left',fill='x',expand=True)
        self.compact_nav=tk.BooleanVar(self.root,value=prefs['compact_nav']);self.restore_recent_setting=tk.BooleanVar(self.root,value=prefs['restore_recent'])
        self.reduce_motion=tk.BooleanVar(self.root,value=prefs['reduce_motion']);self.show_ai_setting=tk.BooleanVar(self.root,value=prefs['show_ai'])
        for label,var in (('使用紧凑导航',self.compact_nav),('启动时恢复上次归档',self.restore_recent_setting),('减少动画',self.reduce_motion),('启动时显示 AI 侧栏',self.show_ai_setting)):
            ttk.Checkbutton(appearance,text=label,variable=var).pack(anchor='w',pady=u(7))
        self.button(appearance,'应用设置',self.request_user_settings,True).pack(anchor='w',pady=u(14))
        self.archive_settings=tk.StringVar(self.root)
        ttk.Label(storage,textvariable=self.archive_settings,style='Hint.TLabel',wraplength=u(760)).pack(anchor='w',pady=(0,u(15)))
        self.storage_root=tk.StringVar(self.root,value=prefs['storage_root'] or str(self.controller.data_dir.resolve()))
        self.default_export_folder=tk.StringVar(self.root,value=prefs['export_folder'])
        for label,var,hint in (('默认存储目录',self.storage_root,'新归档、报告与索引使用此目录；已有文件保留原位。'),
                               ('默认导出目录',self.default_export_folder,'为空时使用默认存储目录下的 exports。')):
            row,_=self.entry_row(storage,label,var)
            self.button(row,'选择目录',lambda value=var:self.pick_settings_folder(value)).pack(side='left',padx=u(6))
            ttk.Label(storage,text=hint,style='Hint.TLabel',wraplength=u(750)).pack(anchor='w',pady=(0,u(12)))
        self.default_export_format=tk.StringVar(self.root,value=prefs['export_format'])
        row=ttk.Frame(storage);row.pack(fill='x',pady=u(8));ttk.Label(row,text='默认导出格式',width=16).pack(side='left')
        ttk.Combobox(row,textvariable=self.default_export_format,values=('HTML 和 TXT','仅 HTML','仅 TXT'),state='readonly',width=24).pack(side='left')
        self.button(storage,'应用设置',self.request_user_settings,True).pack(anchor='w',pady=u(14))
        row=ttk.Frame(storage);row.pack(fill='x',pady=u(14))
        for label,command in (('打开数据文件夹',self.open_data_folder),):
            self.button(row,label,command).pack(side='left',padx=(0,u(6)))
        self.upgrade_button=self.button(storage,'创建升级副本',self.upgrade_archive_copy);# Compatibility handle; upgrades are handled by the Add workflow.
        self.settings_ai_codex=ttk.Frame(ai);self.settings_ai_codex.pack(fill='x')
        self.settings_ai_local=ttk.Frame(ai);self.settings_ai_local.pack(fill='x',pady=(u(26),0))
        self.settings_hint=tk.StringVar(self.root)
        ttk.Label(page,textvariable=self.settings_hint,style='Hint.TLabel',wraplength=u(760)).pack(anchor='w',pady=u(7))
        self.update_archive_settings()

    def pick_settings_folder(self,variable):
        value=filedialog.askdirectory(parent=self.root,title=self.tr('选择目录'),initialdir=variable.get() or str(self.controller.data_dir))
        if value:variable.set(value)

    def collected_preferences(self):
        family=self.font_family.get()
        if family!='系统推荐' and family not in self.theme.available_fonts:raise ValueError(self.tr('请选择有效字体。'))
        return {'theme':THEMES[self.theme_choice.get()],'font_family':'' if family=='系统推荐' else family,'text_size':self.text_size.get(),
                'language':LANGUAGES[self.language_choice.get()],'compact_nav':self.compact_nav.get(),'wheel_speed':self.wheel_speed.get(),
                'restore_recent':self.restore_recent_setting.get(),'reduce_motion':self.reduce_motion.get(),'show_ai':self.show_ai_setting.get(),
                'storage_root':self.storage_root.get().strip(),'export_folder':self.default_export_folder.get().strip(),
                'export_format':self.default_export_format.get()}

    def request_user_settings(self):
        if self.busy:self.settings_hint.set('请等待当前操作完成后再修改设置。');return
        if getattr(self,'settings_apply_job',None):self.root.after_cancel(self.settings_apply_job)
        def apply_latest():
            self.settings_apply_job=None
            if not self.closed:self.apply_user_settings()
        self.settings_apply_job=self.root.after(90,apply_latest)

    def apply_user_settings(self):
        if self.busy:self.settings_hint.set('请等待当前操作完成后再修改设置。');return
        try:
            values=self.collected_preferences();old_root=self.controller.data_dir
            target=Path(values['storage_root']) if values['storage_root'] else self.controller.profile_dir
            changed=target.resolve()!=old_root.resolve()
            if changed and (self.agent_panel.active or self.knowledge_panel.busy):
                raise ValueError('请等 AI 回答或索引操作完成后再更改存储目录。')
            previous=self.ui_settings;self.ui_settings=self.controller.save_user_preferences(values)
            visual=self.theme.update(values['text_size'],values['font_family'],values['theme'],values['language'],values['wheel_speed'])
            language_changed=values['language']!=previous['language']
            if language_changed:self.localizer.switch(values['language'],self.root,self.raw_language_nodes())
            self.copilot_expanded=values['show_ai'];self.adapt_layout();self.update_archive_settings()
            if changed:self.refresh_reports()
            if not self.export_parent.get() or self.export_parent.get()==self.default_export_path(previous):self.export_parent.set(self.default_export_path(values))
            self.export_format.set(values['export_format'])
            if changed:self.knowledge_panel.invalidate('存储目录已改变；请重新更新索引。')
            if visual['fonts'] or visual['palette']:
                self.chat_text.completed_layout=None
                if self.chat_text.winfo_ismapped():self.chat_text.queue_reflow()
                self.agent_panel.layout_dialogue()
                if hasattr(self,'statistics_panel'):self.statistics_panel.schedule_draw()
                if hasattr(self,'help_reader'):self.help_reader.refresh_language()
            if language_changed:
                self.agent_panel._render();self.localize_ui(apply_tree=False)
            self.settings_hint.set('已应用并保存设置。');self.status.set('设置已保存，当前归档位置保留。')
        except Exception as error:
            self.settings_hint.set('设置未保存：'+str(error));messagebox.showerror(self.tr('未保存'),self.tr(str(error)),parent=self.root)

    def default_export_path(self,settings=None):
        settings=settings or self.ui_settings
        root=settings.get('storage_root') or str(self.controller.profile_dir)
        return settings.get('export_folder') or str(Path(root)/'exports')

    def raw_language_nodes(self):
        nodes=[self.chat_title_label,self.owner_box]
        for card,name,preview,*_ in self.contact_tree.cards.values():nodes.extend((name,preview))
        return tuple(nodes)

    def tr(self,value):return self.localizer.tr(value)

    def localize_ui(self,apply_tree=True):
        if apply_tree:self.localizer.apply(self.root,self.raw_language_nodes())
        self.root.title(window_title(self.localizer.language))
        if hasattr(self,'help_reader'):self.help_reader.refresh_language()
        for widget in self.chat_text.body.winfo_children():
            if hasattr(widget,'_date_value'):
                from .message_widgets import date_heading
                value=date_heading(widget._date_value,self.localizer.language)
                widget.configure(text=value)

    def poll_system_theme(self):
        if self.closed:return
        if self.theme.mode=='system' and self.theme.resolved_mode()!=self.theme.active_mode:
            values=self.ui_settings
            self.theme.update(values['text_size'],values['font_family'],values['theme'],values['language'],values['wheel_speed'])
            self.chat_text.completed_layout=None
            if self.chat_text.winfo_ismapped():self.chat_text.queue_reflow()
        self.theme_poll_job=self.root.after(2000,self.poll_system_theme)
