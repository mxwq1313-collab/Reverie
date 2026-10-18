"""归档工作台主壳；浏览、操作面板、既有动作分别由独立模块负责。"""
import queue,time
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
from tkinter.scrolledtext import ScrolledText

from ..branding import APP_NAME,window_title
from .application_controller import ApplicationController
from .browser_panel import BrowserMixin
from .operation_panels import OperationPanels
from .operation_actions import OperationActions
from .copilot_shell import CopilotShell
from .settings_panel import SettingsMixin
from .help_panel import HelpReader
from .icon_button import IconButton
from .localization import Localizer
from .layout_config import configure_changed,row_size
from .slim_scrollbar import SlimScrollbar
from .theme import Theme,PAPER,CANVAS,SIDEBAR,INK,SECONDARY,ACCENT,SELECTED,HOVER,LINE


class ApplicationWindow(SettingsMixin,CopilotShell,BrowserMixin,OperationPanels,OperationActions):
    PAGE_NAMES=('聊天归档','添加记录','导出归档','工具与设置','设置','帮助')
    LEGACY_NAMES=('欢迎','电脑微信','导入文件','可读导出','数据管理','备份检查','报告与设置','Codex 助手','归档与界面','本地知识问答')

    def __init__(self,root,controller=None,data_dir=None,archive=None):
        self.root=root;defer_startup=controller is None;self.controller=controller or ApplicationController(data_dir)
        self.ui_settings=self.controller.user_preferences();self.localizer=Localizer(root,self.ui_settings['language'])
        self.theme=Theme(root,self.ui_settings['text_size'],self.ui_settings['font_family'],self.ui_settings['theme'],self.ui_settings['language'],self.ui_settings['wheel_speed']);u=self.theme.u
        self.busy=False;self.closed=False;self.buttons=[];self.events=queue.Queue();self.accounts=[];self.source_peers=[]
        from .browser_reads import BrowserReads
        self.background_browsing=defer_startup;self.browser_reads=BrowserReads(root,lambda:self.busy)
        self.archive_users=[];self.peer_id=None;self.owner_id=None;self.message_rows=[];self.pages={};self.tab_routes={};self.nav_buttons={}
        self.status=tk.StringVar(root,value='就绪');self.archive_label=tk.StringVar(root,value='未打开归档');self.summary=tk.StringVar(root)
        self.layout_job=None;self.disabled_states=[]
        width=min(u(1240),root.winfo_screenwidth()-u(45));height=min(u(820),root.winfo_screenheight()-u(75))
        root.title(window_title(self.ui_settings['language']));root.geometry(f'{width}x{height}');root.minsize(min(u(820),width),min(u(600),height));root.configure(background=CANVAS)
        root.protocol('WM_DELETE_WINDOW',self.close);root.rowconfigure(1,weight=1);root.columnconfigure(0,weight=1)
        self.header=ttk.Frame(root,padding=(u(16),u(12)));self.header.grid(row=0,column=0,sticky='ew');self.header.columnconfigure(1,weight=1)
        self.brand_label=ttk.Label(self.header,text=APP_NAME,font=self.theme.name);self.brand_label._raw_text=True
        self.brand_label.grid(row=0,column=0,sticky='w',padx=(0,u(24)))
        from .app_logo import install
        install(self)
        self.header_archive=ttk.Label(self.header,textvariable=self.archive_label,style='Hint.TLabel')
        actions=ttk.Frame(self.header);actions.grid(row=0,column=2,sticky='e')
        from .mbti_panel import open_mbti
        self.mbti_button=self.button(actions,'MBTI',lambda:open_mbti(self));self.mbti_button.configure(style='Quiet.TButton',width=-5);self.mbti_button.pack(side='left',padx=(0,u(10)))
        self.copilot_button=self.icon(actions,'codex','Codex 助手',self.toggle_copilot,'Quiet.TButton');self.copilot_button.pack(side='left',padx=(u(6),0))
        main=ttk.Frame(root,style='Canvas.TFrame');main.grid(row=1,column=0,sticky='nsew');main.rowconfigure(0,weight=1);main.columnconfigure(1,weight=1);main.grid_propagate(False)
        self.nav=tk.Frame(main,background=SIDEBAR,width=u(152));self.nav.grid(row=0,column=0,sticky='nsew');self.nav.grid_propagate(False)
        self.nav.columnconfigure(0,weight=1);self.nav.rowconfigure(7,weight=1)
        for index,name in enumerate(self.PAGE_NAMES):
            button=ttk.Button(self.nav,text='工具' if name=='工具与设置' else name,style='Nav.TButton',cursor='hand2',command=lambda value=name:self.show_page(value))
            button.grid(row=index+1,column=0,sticky='ew',padx=u(8),pady=u(4));self.nav_buttons[name]=button;self.buttons.append(button)
        self.capsule_button=self.icon(self.nav,'capsule','时光胶囊',lambda:self.show_page('时光胶囊'),'Quiet.TButton')
        self.capsule_button.grid(row=9,column=0,sticky='w',padx=u(18),pady=(u(8),u(4)))
        self.nav_note=self.icon(self.nav,'stats','统计',lambda:self.show_page('统计'),'Quiet.TButton')
        self.nav_note.grid(row=10,column=0,sticky='w',padx=u(18),pady=(u(4),u(18)))
        from .navigation_feedback import NavigationFeedback
        self.navigation_feedback=NavigationFeedback(self)
        from .resize_viewport import ResizeViewport
        self.resize_viewport=ResizeViewport(main);self.resize_viewport.grid(row=0,column=1,sticky='nsew')
        from .split_controls import split_options
        self.workspace_panes=tk.PanedWindow(self.resize_viewport,**split_options(self.theme))
        self.resize_viewport.attach(self.workspace_panes)
        self.page_host=ttk.Frame(self.workspace_panes,style='Canvas.TFrame');self.workspace_panes.add(self.page_host,minsize=u(420),stretch='always')
        self.page_host.rowconfigure(0,weight=1);self.page_host.columnconfigure(0,weight=1);self.build_copilot_host()
        for name in self.PAGE_NAMES:
            page=ttk.Frame(self.page_host,padding=0 if name=='聊天归档' else u(16));page._lazy_theme=True;page.grid(row=0,column=0,sticky='nsew');self.pages[name]=page;page.grid_remove()
        self.pages['欢迎']=self.pages['聊天归档'];self.pages['可读导出']=self.pages['导出归档']
        self.build_browser();self.build_add();self.build_export();self.build_tools()
        footer=ttk.Frame(root,padding=(u(16),u(8)));footer.grid(row=2,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
        self.status_label=ttk.Label(footer,textvariable=self.status,style='Hint.TLabel',wraplength=u(800));self.status_label.grid(row=0,column=0,sticky='w')
        self.progress=ttk.Progressbar(footer,mode='indeterminate',length=u(80),style='Light.Horizontal.TProgressbar');self.progress.grid(row=0,column=1,sticky='e',padx=u(8))
        self.cancel_button=ttk.Button(footer,text='取消读取',command=self.cancel_reading,state='disabled',style='Quiet.TButton');self.cancel_button.grid(row=0,column=2,sticky='e')
        self.progress.grid_remove();self.cancel_button.grid_remove()
        self.poll_job=root.after(60,self.poll);self.show_page('聊天归档')
        self.startup_job=None
        if defer_startup:
            self.status.set('正在打开归档…');self.show_browser_state('loading')
            self.startup_job=root.after(50,lambda:self.load_initial_archive(archive))
        else:self.load_initial_archive(archive)
        self.workspace_panes.bind('<Configure>',lambda _:self.queue_layout(),add='+')
        root.bind('<Configure>',self.schedule_layout,add='+')
        self.resize_viewport.bind('<Configure>',lambda _:self.queue_layout(),add='+');self.adapt_layout()
        root.bind('<Control-f>',self.focus_message_search,add='+')
        root.bind('<Control-Shift-F>',lambda event:self.focus_message_search(event,True),add='+')
        root.bind('<Escape>',self.browser_escape,add='+')
        root.bind('<Alt-Left>',self.keyboard_return_results,add='+')
        root.bind('<Control-l>',self.copilot_shortcut,add='+')
        from .action_feedback import ActionFeedback
        self.feedback=ActionFeedback(self);self.theme.feedback=self.feedback
        from .workspace_widgets import polish_dialog
        self.dialog_map_binding=root.bind_all('<Map>',lambda event:polish_dialog(event.widget,self) if isinstance(event.widget,tk.Toplevel) else None,add='+')
        self.theme.apply_tree(root);self.localize_ui();self.theme_poll_job=root.after(2000,self.poll_system_theme)

    def load_initial_archive(self,archive=None):
        if self.startup_job:self.root.after_cancel(self.startup_job)
        self.startup_job=None
        if self.closed:return
        if self.busy:
            self.startup_job=self.root.after(50,lambda:self.load_initial_archive(archive));return
        if self.background_browsing:return self.open_browser_archive(archive)
        try:
            if not self.controller.database:
                if archive:self.controller.open_archive(archive)
                elif self.ui_settings['restore_recent']:self.controller.restore_archive()
            self.refresh_archive();self.localize_ui()
            if not self.controller.database:self.status.set('就绪')
        except Exception as error:self.show_browser_state('failed',str(error));self.status.set('已有归档未能打开：'+str(error))

    def icon(self,parent,name,text,command,style='TButton'):
        button=IconButton(parent,self.theme,name,text,command,style);self.buttons.append(button);return button

    def button(self,parent,text,command,primary=False):
        style='Primary.TButton' if primary else 'Danger.TButton' if text.startswith('删除') else 'TButton'
        widget=ttk.Button(parent,text=text,command=command,style=style);self.buttons.append(widget);return widget

    def title(self,page,title,hint=''):
        ttk.Label(page,text=title,style='Title.TLabel').pack(anchor='w',pady=(0,self.theme.u(6)))
        if hint:ttk.Label(page,text=hint,style='Hint.TLabel',wraplength=self.theme.u(800)).pack(anchor='w',pady=(0,self.theme.u(10)))

    def entry_row(self,page,label,variable,width=32):
        row=ttk.Frame(page);row.pack(fill='x',pady=self.theme.u(6))
        ttk.Label(row,text=label,width=12).pack(side='left');entry=ttk.Entry(row,textvariable=variable,width=width)
        entry.pack(side='left',fill='x',expand=True);return row,entry

    def text_panel(self,parent,height=10):
        text=ScrolledText(parent,height=height,wrap='word',font=self.theme.body,background=CANVAS,foreground=INK,relief='flat',padx=self.theme.u(12),pady=self.theme.u(12))
        self.theme.text_surface(text,background=CANVAS)
        text.pack(fill='both',expand=True,pady=self.theme.u(10));text.configure(state='disabled');return text

    def write(self,text,value,append=False):
        text.configure(state='normal')
        if not append:text.delete('1.0','end')
        text.insert('end',value);text.configure(state='disabled')

    def tree(self,parent,columns,widths=None,height=8):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True,pady=self.theme.u(7))
        tree=ttk.Treeview(frame,columns=tuple(columns),show='headings',height=height,selectmode='browse')
        vertical=SlimScrollbar(frame,self.theme,orient='vertical',command=tree.yview);horizontal=SlimScrollbar(frame,self.theme,orient='horizontal',command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set);frame.columnconfigure(0,weight=1);frame.rowconfigure(0,weight=1)
        tree.grid(row=0,column=0,sticky='nsew');vertical.grid(row=0,column=1,sticky='ns');horizontal.grid(row=1,column=0,sticky='ew')
        for index,column in enumerate(columns):tree.heading(column,text=column);tree.column(column,width=self.theme.u(widths[index] if widths else 150),minwidth=self.theme.u(45),stretch=True)
        self.theme.wheel_router.register(tree,tree)
        return tree

    def show_page(self,name):
        if name in ('欢迎','聊天归档'):primary='聊天归档'
        elif name in ('可读导出','导出归档'):primary='导出归档'
        elif name in ('电脑微信','导入文件','添加记录'):primary='添加记录'
        elif name=='帮助':
            primary='帮助'
            if not hasattr(self,'help_reader'):self.help_reader=HelpReader(self,self.pages['帮助'])
        elif name=='时光胶囊':primary='时光胶囊'
        elif name=='统计':
            primary='统计'
            if not hasattr(self,'statistics_panel'):
                from .statistics_panel import StatisticsPanel
                page=ttk.Frame(self.page_host);page.grid(row=0,column=0,sticky='nsew');self.pages['统计']=page
                self.statistics_panel=StatisticsPanel(self,page)
        elif name in ('设置','归档与界面','存储设置','AI设置','Codex 助手','报告与设置'):primary='设置'
        else:primary='工具与设置'
        if name in self.tab_routes:
            notebook,tab=self.tab_routes[name];notebook.select(tab)
        previous=getattr(self,'current_page',None)
        if previous!=primary:
            if previous in self.pages:self.pages[previous].grid_remove()
            self.pages[primary].grid()
        self.pages[primary].tkraise();self.current_page=primary;self.current_subpage=name
        if primary=='聊天归档':self.render_pending_browser()
        self.nav_note.toggled=primary=='统计';self.nav_note.refresh_icon()
        self.capsule_button.toggled=primary=='时光胶囊';self.capsule_button.refresh_icon()
        if primary=='时光胶囊':self.toolbox_panel.activate('时光胶囊')
        elif primary=='工具与设置':
            selected=self.tools_notebook.select()
            route=next((key for key,(notebook,tab) in self.tab_routes.items() if notebook is self.tools_notebook and str(tab)==selected),None)
            self.toolbox_panel.activate(route)
            if route=='数据管理':self.refresh_management_messages()
        else:self.toolbox_panel.activate(None)
        if primary=='统计':self.statistics_panel.refresh()
        if name=='Codex 助手':self.open_copilot(False)
        for value,button in self.nav_buttons.items():
            button.configure(style='SelectedNav.TButton' if value==primary else 'Nav.TButton')
            self.theme.scope_font(button,'TButton')
        self.navigation_feedback.select(self.nav_note if primary=='统计' else self.capsule_button if primary=='时光胶囊' else self.nav_buttons.get(primary))
        # Existing controls are already localized; only newly built pages need a walk.
        localized=getattr(self,'_localized_pages',set())
        if primary not in localized:
            self.localizer.apply(self.pages[primary],self.raw_language_nodes())
            localized.add(primary);self._localized_pages=localized

    def schedule_layout(self,event):
        if event.widget is not self.root or self.closed:return
        size=(event.width,event.height)
        if size==getattr(self,'resize_event_size',None):return
        self.resize_event_size=size
        self.queue_layout()

    def queue_layout(self):
        # Keep one pending pass, reading the latest geometry after Tk lays out children.
        # Never freeze/unmap the workspace or restart a trailing-edge resize timer.
        if self.closed or self.layout_job is not None:return
        self.layout_job=self.root.after_idle(self.adapt_layout)

    def adapt_layout(self):
        if self.layout_job:
            try:self.root.after_cancel(self.layout_job)
            except tk.TclError:pass
        self.layout_job=None
        if self.closed:return
        key=(self.root.winfo_width(),self.resize_viewport.winfo_width(),self.workspace_panes.winfo_width(),self.browser_panes.winfo_width(),self.theme.generation,getattr(self,'copilot_expanded',False),getattr(self,'copilot_width',0),self.compact_nav.get() if hasattr(self,'compact_nav') else False,getattr(self,'current_page',None))
        if key==getattr(self,'layout_key',None):return
        self.layout_key=key
        width=max(self.root.winfo_width(),self.theme.u(820))/self.theme.scale
        reading_width=width-(self.copilot_width if getattr(self,'copilot_expanded',False) else 0)
        compact=reading_width<1020 or hasattr(self,'compact_nav') and self.compact_nav.get()
        nav_width=max(94,self.theme.text_size*5+20) if compact else max(152,self.theme.text_size*6+20)
        configure_changed(self.nav,width=self.theme.u(nav_width));self.layout_browser_split()
        short={'聊天归档':'聊天','添加记录':'添加','导出归档':'导出','工具与设置':'工具','设置':'设置','帮助':'帮助'}
        for name,button in self.nav_buttons.items():self.localizer.text(button,short[name] if compact else ('工具' if name=='工具与设置' else name));configure_changed(button,width=-4 if compact else -8)
        self.localizer.text(self.nav_note,'统计')
        configure_changed(self.header_archive,wraplength=self.theme.u(max(120,width-440)))
        for label in (self.conversation_title,self.chat_title_label,self.copilot_title):configure_changed(label,font=self.theme.section)
        for section in (self.conversation_heading,self.chat_header,self.copilot_header):
            row_size(section,0,self.theme.control_height)
        configure_changed(self.status_label,wraplength=self.theme.u(max(260,width-260)))
        self.fit_chat_footer()
        self.layout_copilot()
        row_size(self.chat_header,1,self.theme.control_height+self.theme.u(8))
        row_size(self.contact_filter_row,0,self.theme.control_height)
        self.fit_chat_title();self.fit_tool_tabs()

    def descendants(self,parent):
        for child in parent.winfo_children():
            yield child;yield from self.descendants(child)

    def run(self,label,work,done):
        if self.busy:return
        while not self.controller.operation_progress.empty():self.controller.operation_progress.get_nowait()
        self.busy=True;self.controller.cancel_event.clear();self.status.set(label);self.progress.grid();self.progress.configure(mode='indeterminate',value=0)
        if not self.ui_settings['reduce_motion']:self.progress.start(12)
        self.disabled_states=[]
        self.active_card=None  # Result cards become visible only after a real preview/import report.
        if self.active_card:
            self.active_card.activate();self.active_card.state.set(label)
            for value in self.active_card.values:value.set('—')
        self.export_running='保存离线' in label
        if self.export_running:self.write(self.export_result,'正在导出所选范围内的消息与附件…')
        for widget in self.descendants(self.root):
            if widget in (self.cancel_button,self.copilot_button,self.copilot_hide_button,self.nav_note,self.capsule_button,*self.nav_buttons.values()):continue
            if widget.winfo_class() in ('TButton','Button','TEntry','TCombobox','TCheckbutton','TSpinbox'):
                try:self.disabled_states.append((widget,str(widget.cget('state'))));widget.configure(state='disabled')
                except tk.TclError:pass
        cancelable=any(value in label for value in ('微信','账号','联系人'))
        self.cancel_button.configure(state='normal' if cancelable else 'disabled')
        if cancelable:self.cancel_button.grid()
        else:self.cancel_button.grid_remove()
        def execute():
            try:self.events.put(('done',done,work()))
            except Exception as error:self.events.put(('error',None,str(error)))
        threading.Thread(target=execute,daemon=False,name='archive-operation').start()

    def poll(self):
        if self.closed:return
        latest=None
        try:
            while True:latest=self.controller.operation_progress.get_nowait()
        except queue.Empty:pass
        if self.busy and latest:self.status.set(latest)
        try:
            while True:
                kind,callback,result=self.events.get_nowait();self.busy=False;self.progress.stop();self.progress.grid_remove();self.cancel_button.configure(state='disabled');self.cancel_button.grid_remove()
                for widget,state in self.disabled_states:
                    try:widget.configure(state=state)
                    except tk.TclError:pass
                self.disabled_states=[]
                if kind=='error':
                    if self.active_card:self.active_card.state.set('本次操作未完成，计数尚未确认。')
                    if self.export_running:self.write(self.export_result,'本次导出未完成：'+result)
                    self.status.set('未完成：'+result);messagebox.showerror('操作未完成',result,parent=self.root)
                else:
                    try:
                        callback(result)
                        if self.active_card and self.active_card.state.get().startswith('正在'):self.active_card.state.set('当前阶段完成；归档完成后显示新增、重复等计数。')
                    except Exception as error:self.status.set('显示结果失败：'+str(error))
        except queue.Empty:pass
        self.poll_job=self.root.after(60 if self.busy else 250,self.poll)

    def cancel_reading(self):
        if self.controller.writing and not self.controller.streaming:self.status.set('正在提交归档，请等待保存完成。');return
        if self.controller.streaming:
            self.controller.cancel_event.set();self.status.set('当前保存完成后停止后续批次；已入库记录保留，可恢复。');return
        self.controller.cancel_event.set();self.status.set('正在取消读取…')

    def ensure_archive(self):
        if self.controller.database:return
        default=self.controller.data_dir/'chat.db'
        if default.exists():self.controller.open_archive(default)
        else:self.controller.new_archive(default)
        self.refresh_archive()

    def open_archive(self):
        path=filedialog.askopenfilename(parent=self.root,title='打开已有归档',filetypes=[('项目归档','*.db *.sqlite *.sqlite3')])
        if path:
            if self.background_browsing:self.open_browser_archive(path);return
            try:self.controller.open_archive(path);self.refresh_archive();self.show_page('聊天归档')
            except Exception as error:messagebox.showerror('无法打开归档',str(error),parent=self.root)

    def new_archive(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='新建归档（不会覆盖已有文件）',initialdir=str(self.controller.data_dir),initialfile='chat.db',defaultextension='.db',filetypes=[('项目归档','*.db')])
        if path:
            try:self.controller.new_archive(path,rich=True);self.refresh_archive();self.show_page('聊天归档')
            except Exception as error:messagebox.showerror('未创建归档',str(error),parent=self.root)

    def restore_recent(self):
        try:
            if self.controller.restore_archive():self.refresh_archive();self.show_page('聊天归档')
            else:self.status.set('没有可恢复的有效归档，请打开已有归档。')
        except Exception as error:self.status.set('恢复未完成：'+str(error))

    def close(self):
        if self.closed:return
        if self.busy:self.status.set('正在处理数据，请等完成后关闭。');return
        self.cancel_copilot_drag()
        self.persist_copilot_layout()
        if hasattr(self,'feedback'):self.feedback.close()
        if hasattr(self,'source_renderer'):self.source_renderer.cancel()
        if getattr(self,'settings_apply_job',None):self.root.after_cancel(self.settings_apply_job);self.settings_apply_job=None
        if hasattr(self,'forward_image_service'):self.forward_image_service.close()
        if hasattr(self,'thumbnail_service'):self.thumbnail_service.close()
        self.browser_reads.close()
        if getattr(self,'management_job',None):self.root.after_cancel(self.management_job);self.management_job=None
        self.navigation_feedback.close()
        if hasattr(self,'statistics_panel'):self.statistics_panel.close()
        self.closed=True;self.root.after_cancel(self.theme_poll_job);self.agent_panel.close();self.knowledge_panel.close();self.root.after_cancel(self.poll_job)
        if self.startup_job:self.root.after_cancel(self.startup_job)
        if self.layout_job:self.root.after_cancel(self.layout_job)
        self.root.update_idletasks();self.theme.close();self.root.destroy()
