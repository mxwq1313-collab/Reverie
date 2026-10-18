from .media_widgets import present_content
"""聊天工作台的三栏内容、视图恢复、搜索和只读上下文。"""
import tkinter as tk
import time
from tkinter import ttk
from .message_widgets import ContactList,BubbleTimeline
from .theme import PAPER,CANVAS,INK,SECONDARY
from .browser_reads import AsyncBrowserMixin


class BrowserMixin(AsyncBrowserMixin):
    def build_browser(self):
        page=self.pages['聊天归档'];u=self.theme.u
        page.columnconfigure(0,weight=1);page.rowconfigure(0,weight=1)
        from .split_controls import split_options,bind_split
        self.browser_panes=tk.PanedWindow(page,**split_options(self.theme));self.browser_panes.grid(row=0,column=0,sticky='nsew')
        self.contacts_width=self.controller.browser_layout()['width']
        self.browser_panes.bind('<Configure>',lambda _:self.queue_layout(),add='+')
        bind_split(self,self.browser_panes,self.save_browser_sash,self.reset_browser_sash)
        self.conversation_column=ttk.Frame(self.browser_panes,width=u(self.contacts_width),padding=(u(16),u(16)));self.browser_panes.add(self.conversation_column,minsize=u(140),stretch='never');self.conversation_column.pack_propagate(False)
        column=self.conversation_column
        row=ttk.Frame(column);row.pack(fill='x',pady=(0,u(8)));row.columnconfigure(0,weight=1);row.rowconfigure(0,minsize=self.theme.control_height);self.conversation_heading=row
        self.conversation_title=ttk.Label(row,text='会话',font=self.theme.section);self.conversation_title.grid(row=0,column=0,sticky='w')
        self.contact_count=tk.StringVar(self.root,value='0 个')
        self.owner_var=tk.StringVar(self.root);self.owner_box=ttk.Combobox(column,textvariable=self.owner_var,state='readonly')
        self.owner_box._raw_values=True
        self.owner_box.pack(fill='x');self.owner_box.bind('<<ComboboxSelected>>',lambda _:self.change_owner())
        from .search_entry import SearchEntry
        contact_filters=ttk.Frame(column);contact_filters.pack(fill='x',pady=(u(16),u(12)));contact_filters.columnconfigure(0,weight=1)
        self.contact_keyword=tk.StringVar(self.root);self.contact_entry=SearchEntry(contact_filters,self.theme,self.contact_keyword,'搜索联系人…',self.load_contacts)
        self.contact_entry.grid(row=0,column=0,columnspan=2,sticky='ew')
        self.contact_filter_row=ttk.Frame(contact_filters);self.contact_filter_row.grid(row=1,column=0,columnspan=2,sticky='ew',pady=(u(8),0));self.contact_filter_row.columnconfigure(0,weight=1)
        ttk.Label(self.contact_filter_row,textvariable=self.contact_count,style='Hint.TLabel').grid(row=0,column=0,sticky='w')
        self.refresh_contacts_button=self.icon(self.contact_filter_row,'refresh','刷新联系人',self.refresh_archive,'Quiet.TButton');self.refresh_contacts_button.grid(row=0,column=1,sticky='e')
        self.avatar_refresh_button=self.button(self.contact_filter_row,'更新头像',self.update_wechat_avatars);self.avatar_refresh_button.configure(style='Quiet.TButton',width=-3);self.avatar_refresh_button.grid(row=0,column=2,sticky='e',padx=(self.theme.u(5),0))
        self.contact_tree=ContactList(column,self.theme,self.select_contact);self.contact_tree.pack(fill='both',expand=True)
        self.contact_tree.canvas.bind('<Control-f>',self.focus_message_search,add='+')
        self.contact_tree.canvas.bind('<Control-Shift-F>',lambda event:self.focus_message_search(event,True),add='+')
        right=ttk.Frame(self.browser_panes,style='Canvas.TFrame');self.message_content_column=right;self.browser_panes.add(right,minsize=u(220),stretch='always');right.columnconfigure(0,weight=1);right.rowconfigure(3,weight=1)
        header=ttk.Frame(right,padding=(u(16),u(16)));header.grid(row=0,column=0,sticky='ew');header.columnconfigure(0,weight=1);self.chat_header=header
        self.chat_title=tk.StringVar(self.root,value='聊天归档');self.chat_subtitle=tk.StringVar(self.root,value='私聊消息')
        self.chat_title_label=ttk.Label(header,font=self.theme.section);self.chat_title_label.grid(row=0,column=0,sticky='w')
        self.chat_title.trace_add('write',lambda *_:self.fit_chat_title())
        self.chat_header.bind('<Configure>',lambda _:self.fit_chat_title(),add='+')
        ttk.Label(header,textvariable=self.chat_subtitle,style='Hint.TLabel').grid(row=1,column=0,sticky='w',pady=(u(3),0))
        self.conversation_export_button=self.button(header,'导出',lambda:self.prepare_export('当前会话'))
        self.conversation_export_button.configure(style='Quiet.TButton',width=-3)
        self.conversation_export_button.grid(row=0,column=1,sticky='e')
        self.ask_ai_button=self.button(header,'询问 AI',self.ask_current_conversation)
        # The global top-right Codex button is the sole assistant entry.
        self.return_results_button=self.button(header,'← 返回搜索结果',self.return_search_results)
        self.return_results_button.grid(row=2,column=0,sticky='w',pady=(u(5),0));self.return_results_button.grid_remove()
        self.search_return_state=None
        filters=ttk.Frame(right,padding=(u(16),0,u(16),u(12)));filters.grid(row=1,column=0,sticky='ew');filters.columnconfigure(0,weight=1)
        self.search_word=tk.StringVar(self.root);self.search_entry=SearchEntry(filters,self.theme,self.search_word,'搜索聊天记录…',self.load_messages)
        self.search_entry.grid(row=0,column=0,columnspan=3,sticky='ew')
        self.search_placeholder=self.search_entry.placeholder_label
        self.search_scope=tk.StringVar(self.root,value='当前会话');self.search_box=ttk.Combobox(filters,textvariable=self.search_scope,values=('当前会话','全部会话'),state='readonly',width=9)
        self.search_box.grid(row=1,column=0,sticky='w',pady=(u(8),0));self.search_box.configure(width=10)
        self.search_button=self.button(filters,'搜索',self.load_messages);self.search_button.configure(style='Quiet.TButton');self.search_button.grid_remove()
        self.date_button=self.button(filters,'日期',self.toggle_dates);self.date_button._symbol_only=True;self.date_button.grid(row=1,column=2,sticky='e',pady=(u(8),0))
        # Use natural text width; the theme's nine-character button minimum can hide the entry beside a docked copilot.
        self.search_button.configure(width=-4);self.date_button.configure(width=-4)
        self.dates_expanded=False;self.date_controls=ttk.Frame(right,padding=(u(16),0));self.date_controls.columnconfigure(4,weight=1)
        self.start_date=tk.StringVar(self.root);self.end_date=tk.StringVar(self.root)
        ttk.Label(self.date_controls,text='从',style='Hint.TLabel').grid(row=0,column=0,padx=(0,u(4)))
        self.start_entry=ttk.Entry(self.date_controls,textvariable=self.start_date,width=11);self.start_entry.grid(row=0,column=1)
        ttk.Label(self.date_controls,text='至',style='Hint.TLabel').grid(row=0,column=2,padx=u(5))
        self.end_entry=ttk.Entry(self.date_controls,textvariable=self.end_date,width=11);self.end_entry.grid(row=0,column=3)
        self.start_entry.bind('<Return>',lambda _:self.load_messages());self.end_entry.bind('<Return>',lambda _:self.load_messages())
        self.clear_button=self.button(self.date_controls,'清除筛选',self.clear_filters);self.clear_button.grid(row=0,column=4,sticky='e',padx=u(5))
        ttk.Label(self.date_controls,text='YYYY-MM-DD · 包含起止日期（北京时间）',style='Hint.TLabel').grid(row=1,column=0,columnspan=5,sticky='w',pady=(u(4),u(8)))
        self.chat_text=BubbleTimeline(right,self.theme);self.chat_text.app=self;self.chat_text.grid(row=3,column=0,sticky='nsew')
        footer=ttk.Frame(right,padding=(u(16),u(8)));footer.grid(row=4,column=0,sticky='ew');footer.columnconfigure(0,weight=1)
        self.chat_info=tk.StringVar(self.root,value='尚未打开归档');self.count_label=ttk.Label(footer,textvariable=self.chat_info,style='Hint.TLabel');self.count_label.grid(row=0,column=0,sticky='w')
        self.more_button=self.button(footer,'加载更多',lambda:self.load_messages(more=True));self.more_button.grid(row=0,column=1,sticky='e')
        self.chat_footer=footer;footer.bind('<Configure>',self.fit_chat_footer,add='+')
        self.contact_count.trace_add('write',lambda *_:self.schedule_contact_layout())
        self.loaded_offset=0;self.message_total=0;self.contact_rows=[]
        self.show_browser_state('no_archive')

    def schedule_contact_layout(self):
        self.layout_key=None;self.queue_layout()
    def browser_minimums(self):
        u=self.theme.u
        return (max(u(180),self.contact_filter_row.winfo_reqwidth()+u(36)),
                max(u(220),self.search_box.winfo_reqwidth()+self.date_button.winfo_reqwidth()+u(40)))
    def fit_chat_footer(self,event=None):
        if not hasattr(self,'chat_footer') or self.chat_footer.winfo_width()<2:return
        from .layout_config import configure_changed
        room=max(self.theme.u(40),self.chat_footer.winfo_width()-self.more_button.winfo_reqwidth()-self.theme.u(40))
        configure_changed(self.count_label,wraplength=room)
    def layout_browser_split(self):
        if not hasattr(self,'browser_panes') or not self.browser_panes.winfo_ismapped():return
        panes=self.browser_panes;u=self.theme.u;width=panes.winfo_width()
        minimum,reading=self.browser_minimums()
        key=(width,self.theme.generation,self.contacts_width,minimum,reading)
        if key==getattr(self,'browser_split_key',None):return
        self.browser_split_key=key
        from .layout_config import configure_changed
        configure_changed(panes,sashwidth=u(8),background=self.theme.palette['LINE'],proxybackground=self.theme.palette['ACCENT'])
        if int(panes.panecget(self.conversation_column,'minsize'))!=minimum:panes.paneconfigure(self.conversation_column,minsize=minimum)
        if int(panes.panecget(self.message_content_column,'minsize'))!=reading:panes.paneconfigure(self.message_content_column,minsize=reading)
        target=min(u(self.contacts_width),max(minimum,width-reading-u(8)))
        if not getattr(panes,'_split_dragging',False) and abs(panes.sash_coord(0)[0]-target)>1:panes.sash_place(0,target,0)
    def save_browser_sash(self):
        if not self.browser_panes.winfo_ismapped():return
        self.contacts_width=max(140,min(2048,round(self.browser_panes.sash_coord(0)[0]/self.theme.scale)))
        self.controller.save_browser_layout(self.contacts_width);self.browser_split_key=None
    def reset_browser_sash(self):
        self.contacts_width=270;self.controller.save_browser_layout(270);self.browser_split_key=None;self.layout_browser_split();return 'break'

    def fit_chat_title(self):
        width=self.chat_header.winfo_width()
        if width<5:width=self.theme.u(600)
        actions=self.conversation_export_button.winfo_reqwidth()
        room=max(self.theme.u(40),width-actions-self.theme.u(40))
        key=(self.chat_title.get(),room,self.theme.generation)
        if key==getattr(self,'chat_title_fit_key',None):return
        self.chat_title_fit_key=key
        from .layout_config import configure_changed
        configure_changed(self.chat_title_label,text=self.theme.elide(key[0],room,renderer=self.theme.section_font))

    def show_browser_state(self,kind,error=''):
        self.message_rows=[];self.message_total=0;self.loaded_offset=0;self.more_button.configure(state='disabled')
        self.conversation_export_button.configure(state='normal' if self.peer_id is not None else 'disabled')
        states={
            'loading':('正在打开归档…','',()),
            'no_archive':('打开自己的聊天归档','打开已有归档，或添加聊天记录后开始浏览。',(('打开已有归档',self.open_archive),('添加聊天记录',lambda:self.show_page('添加记录')))),
            'no_users':('归档还没有聊天记录','添加已有文件，或从电脑微信读取所选私聊。',(('添加聊天记录',lambda:self.show_page('添加记录')),)),
            'no_chats':('当前身份暂无会话','可以切换查看身份，或为这个归档添加聊天记录。',(('添加聊天记录',lambda:self.show_page('添加记录')),)),
            'no_contacts':('没有匹配的联系人','清除联系人搜索，或换一个关键词。',(('清除联系人搜索',self.clear_contact_search),)),
            'no_matches':('没有匹配的消息','调整关键词或日期；清除筛选可恢复当前会话。',(('清除筛选',self.clear_filters),)),
            'failed':('加载未完成',error or '检查归档是否可访问，再重试。',(('重试加载',self.load_messages),('打开归档',self.open_archive)))
        }
        title,hint,actions=states[kind];self.browser_state=kind;self.chat_text.show_state(title,hint,actions)
        self.chat_info.set('全部匹配 0 条 · 当前加载 0 条' if kind=='no_matches' else title)
        if hasattr(self,'message_tree'):self.sync_management_messages()

    def refresh_archive(self):
        stats=getattr(self,'statistics_panel',None)
        if stats:stats.cache=None;stats.data=None;stats.clear()
        self.notify_copilot_binding()
        self.update_source_capabilities()
        if not self.controller.database:
            self.archive_label.set('未打开归档');self.show_browser_state('no_archive');return
        info=self.controller.overview();path=self.controller.database
        changed=path!=getattr(self,'view_archive',None);self.view_archive=path
        if changed:
            self.forget_search_return();self.contact_tree.avatar_service.clear();self.contact_tree._elide_cache.clear()
        self.archive_label.set(path.name);self.summary.set(f"{info['users']} 个身份 · {info['messages']} 条已归档消息")
        self.archive_users=self.controller.users();labels=[f"{row['nickname']} · {row['id']}" for row in self.archive_users];self.owner_box['values']=labels
        for key in self.user_tree.get_children():self.user_tree.delete(key)
        for row in self.archive_users:self.user_tree.insert('','end',iid=str(row['id']),values=(row['id'],row['nickname'],row['wxid']))
        if not labels:
            self.owner_id=None;self.peer_id=None;self.owner_var.set('');self.contact_tree.set_rows([]);self.show_browser_state('no_users')
        else:
            saved=self.controller.view_state() if changed else {'owner_id':self.owner_id,'peer_id':self.peer_id}
            ids=[row['id'] for row in self.archive_users];chosen=saved.get('owner_id')
            self.owner_id=chosen if type(chosen) is int and chosen in ids else ids[0]
            self.peer_id=saved.get('peer_id') if type(saved.get('peer_id')) is int else None
            self.owner_box.current(ids.index(self.owner_id))
            if changed:self.search_word.set('');self.start_date.set('');self.end_date.set('');self.search_scope.set('当前会话');self.contact_keyword.set('')
            self.load_contacts()
        self.refresh_reports();self.update_archive_settings();self.update_export_caption();self.status.set('归档已就绪。')
        if stats and self.current_page=='统计':stats.refresh()

    def remember_view(self):
        if self.owner_id is not None:
            try:self.controller.save_view(self.owner_id,self.peer_id)
            except OSError:self.status.set('记录已加载，但上次查看位置未能保存。')

    def change_owner(self):
        index=self.owner_box.current()
        if index>=0:
            self.forget_search_return()
            self.owner_id=self.archive_users[index]['id'];self.peer_id=None
            self.notify_copilot_binding()
            self.search_scope.set('当前会话');self.search_word.set('');self.start_date.set('');self.end_date.set('');self.contact_keyword.set('');self.load_contacts()

    def load_contacts(self,_prepared=None):
        if self.background_browsing and _prepared is None:return self.read_contacts_async()
        if self.owner_id is None:return
        try:rows=[row for row in (self.controller.contacts(self.owner_id,self.contact_keyword.get()) if _prepared is None else _prepared) if row['message_count']>0]
        except Exception as error:self.show_browser_state('failed',str(error));return
        self.contact_rows=rows;self.contact_count.set(f'{len(rows)} 个')
        ids=[row['id'] for row in rows]
        self.peer_id=self.peer_id if self.peer_id in ids else ids[0] if ids else None
        self.notify_copilot_binding()
        render=self.contact_tree.set_rows_incremental if self.background_browsing else self.contact_tree.set_rows
        render(rows,self.peer_id)
        if ids:self.load_messages();self.remember_view()
        else:self.chat_title.set('聊天归档');self.show_browser_state('no_contacts' if self.contact_keyword.get() else 'no_chats')

    def clear_contact_search(self):self.contact_keyword.set('');self.load_contacts()

    def select_contact(self,event=None):
        selected=self.contact_tree.selection()
        if selected:
            self.forget_search_return()
            self.peer_id=int(selected[0]);self.notify_copilot_binding();self.search_scope.set('当前会话');self.load_messages();self.remember_view()

    def toggle_dates(self):
        self.dates_expanded=not self.dates_expanded
        if self.dates_expanded:self.date_controls.grid(row=2,column=0,sticky='ew');self.date_button.configure(text='收起日期')
        else:self.date_controls.grid_remove();self.date_button.configure(text='日期')

    def clear_filters(self):self.search_word.set('');self.start_date.set('');self.end_date.set('');self.load_messages()

    def load_messages(self,more=False,_prepared=None):
        if self.background_browsing and _prepared is None:return self.read_messages_async(more)
        if not more:self.forget_search_return()
        if self.owner_id is None:
            self.show_browser_state('no_archive' if not self.controller.database else 'no_users');return
        all_chats=self.search_scope.get()=='全部会话';peer=None if all_chats else self.peer_id
        if peer is None and not all_chats:self.show_browser_state('no_chats');return
        query=(self.owner_id,peer,self.search_word.get(),self.start_date.get(),self.end_date.get())
        if more and query!=getattr(self,'loaded_query',None):more=False
        offset=self.loaded_offset+len(self.message_rows) if more else 0
        try:
            source_token=self.controller.archive_view_token()
            if more and source_token!=getattr(self,'loaded_token',None):
                self.forget_search_return();self.status.set('归档已变化，不能追加旧分页；请重新搜索。');return
            result=self.controller.messages(self.owner_id,peer,self.search_word.get(),self.start_date.get(),self.end_date.get(),offset) if _prepared is None else _prepared
            if source_token!=self.controller.archive_view_token():raise OSError('查询期间归档已变化，请重新搜索。')
        except Exception as error:
            if more:self.status.set('加载更多失败：'+str(error)+'；已加载内容保留，可重试。')
            else:self.show_browser_state('failed',str(error))
            return
        self.loaded_offset=offset if not more else self.loaded_offset
        self.loaded_query=query
        self.loaded_token=source_token
        self.message_rows=self.message_rows+result['items'] if more else list(result['items'])
        self.message_total=result['total'];self.browser_state='messages' if self.message_rows else 'no_matches'
        if not self.message_rows:self.show_browser_state('no_matches')
        else:
            if self.background_browsing and self.current_page!='聊天归档':self.pending_browser_render=True
            else:
                render=self.chat_text.set_rows_incremental if self.background_browsing else self.chat_text.set_rows
                render(result['items'],self.owner_id,self.search_word.get(),all_chats,self.show_context,append=more)
            self.update_message_count(result['has_more'])
        selected=next((row for row in self.contact_rows if row['id']==self.peer_id),None)
        self.chat_title.set('全部会话搜索' if all_chats else selected['nickname'] if selected else '聊天归档')
        self.chat_subtitle.set(('群聊' if self.peer_id is not None and self.peer_id<0 else '私聊消息')+(' · 结果可查看所属会话上下文' if all_chats else ''))
        self.conversation_export_button.configure(state='disabled' if all_chats or self.peer_id is None else 'normal')
        self.ask_ai_button.configure(state='disabled' if self.peer_id is not None and self.peer_id<0 else 'normal')
        self.sync_management_messages();self.update_export_caption()
        if not self.dates_expanded:self.date_button.configure(text='日期 · 已筛选' if self.start_date.get() or self.end_date.get() else '日期')

    def update_message_count(self,has_more):
        extra=f' · 从第 {self.loaded_offset+1} 条起' if self.loaded_offset else ''
        self.chat_info.set(f'全部匹配 {self.message_total} 条 · 当前加载 {len(self.message_rows)} 条'+extra)
        self.more_button.configure(state='normal' if has_more and not getattr(self.chat_text,'rendering',False) and not self.busy else 'disabled')

    def render_pending_browser(self):
        if getattr(self,'pending_browser_render',False):
            self.pending_browser_render=False;query=self.loaded_query
            self.chat_text.set_rows_incremental(self.message_rows,self.owner_id,query[2],query[1] is None,self.show_context)

    def management_visible(self):
        if getattr(self,'current_page',None)!='工具与设置':return False
        notebook,tab=self.tab_routes['数据管理']
        return notebook.select()==str(tab)

    def sync_management_messages(self):
        self._management_messages_dirty=True
        self._management_revision=getattr(self,'_management_revision',0)+1
        if getattr(self,'management_job',None):
            self.root.after_cancel(self.management_job);self.management_job=None
        if self.management_visible():self.refresh_management_messages()

    def refresh_management_messages(self):
        if not getattr(self,'_management_messages_dirty',False) or not self.management_visible():return
        if getattr(self,'management_job',None):return
        revision=self._management_revision
        rows=iter(tuple(self.message_rows))
        self.message_tree.delete(*self.message_tree.get_children())
        def batch():
            self.management_job=None
            if self.closed or revision!=self._management_revision:return
            if not self.management_visible():return
            started=time.perf_counter()
            for row in rows:
                self.message_tree.insert('','end',iid=str(row['id']),values=(row['id'],row['create_time'],row['sender_name'],row['receiver_name'],present_content(row)[:80].replace('\n',' ')))
                if self.background_browsing and time.perf_counter()-started>.006:
                    self.management_job=self.root.after(1,batch);return
            self._management_messages_dirty=False
        if self.background_browsing:self.management_job=self.root.after(1,batch)
        else:batch()

    def show_context(self,message_id,_prepared=None):
        if self.background_browsing and _prepared is None:
            owner=self.owner_id;token=self.controller.archive_view_token();reader=self.controller.read_snapshot(None)
            cached=list(self.contact_rows) if not self.contact_keyword.get() else None
            def work(cancel):
                reader._read_cancel=cancel
                result=reader.message_context(owner,message_id)
                result['_contacts']=cached if cached is not None else reader.contacts(owner)
                return result
            def done(result):
                if self.owner_id==owner and self.controller.archive_view_token()==token:self.show_context(message_id,_prepared=result)
            self.status.set('正在定位原始消息…');self.browser_reads.submit('context',work,done,self.read_problem);return
        try:result=self.controller.message_context(self.owner_id,message_id) if _prepared is None else _prepared
        except Exception as error:self.status.set('上下文未加载：'+str(error));return
        query=getattr(self,'loaded_query',None)
        if self.search_return_state is None and query and (query[1] is None or any(query[2:])):
            self.search_return_state={'query':query,'token':self.loaded_token,'peer_id':self.peer_id,
                'rows':list(self.message_rows),'total':self.message_total,'offset':self.loaded_offset,
                'contact_keyword':self.contact_keyword.get(),'contact_rows':list(self.contact_rows),'title':self.chat_title.get(),'subtitle':self.chat_subtitle.get(),
                'dates_expanded':self.dates_expanded,'top':self.chat_text.canvas.canvasy(0)}
            self.return_results_button.grid()
        self.peer_id=result['peer_id'];self.search_word.set('');self.start_date.set('');self.end_date.set('');self.search_scope.set('当前会话')
        self.notify_copilot_binding()
        self.contact_keyword.set('')
        contacts=result['_contacts'] if '_contacts' in result else self.controller.contacts(self.owner_id)
        self.contact_rows=[row for row in contacts if row['message_count']>0]
        render=self.contact_tree.set_rows_incremental if self.background_browsing else self.contact_tree.set_rows
        render(self.contact_rows,self.peer_id);self.contact_count.set(f'{len(self.contact_rows)} 个')
        self.message_rows=list(result['items']);self.loaded_offset=result['offset'];self.message_total=result['total'];self.browser_state='messages'
        self.loaded_query=(self.owner_id,self.peer_id,'','','')
        if self.background_browsing:
            self.chat_text.set_rows_incremental(result['items'],self.owner_id);self.chat_text.after_render(lambda:self.chat_text.see_message(message_id))
        else:self.chat_text.set_rows(result['items'],self.owner_id);self.chat_text.see_message(message_id)
        peer=next((row for row in self.contact_rows if row['id']==self.peer_id),{'nickname':'聊天归档'});self.chat_title.set(peer['nickname']);self.chat_subtitle.set(f'消息 #{message_id} 的原会话上下文')
        self.update_message_count(result['has_more']);self.conversation_export_button.configure(state='normal');self.sync_management_messages();self.remember_view()
        self.show_page('聊天归档');self.status.set('已定位原消息；显示的是未经过滤的原会话上下文。')

    def forget_search_return(self):
        self.search_return_state=None
        if hasattr(self,'return_results_button'):self.return_results_button.grid_remove()

    def focus_message_search(self,event=None,all_chats=False):
        if getattr(self,'current_page',None)=='帮助' and not all_chats:
            self.help_reader.entry.focus_set();return 'break'
        if self.current_page!='聊天归档' or self.busy:return
        if all_chats:self.search_scope.set('全部会话')
        if getattr(self,'copilot_mode',None)=='drawer':self.hide_copilot()
        self.focus_search_field();self.root.after_idle(self.focus_search_field);return 'break'

    def focus_search_field(self):
        if not self.closed and self.current_page=='聊天归档' and not self.busy:
            self.search_entry.focus_set();self.search_entry.selection_range(0,'end')

    def browser_escape(self,event=None):
        if self.current_page!='聊天归档' or self.busy:return
        if self.search_return_state:self.return_search_results();return 'break'
        if event is not None and event.widget is self.contact_entry and self.contact_keyword.get():
            self.clear_contact_search();return 'break'
        if self.search_word.get() or self.start_date.get() or self.end_date.get():self.clear_filters();return 'break'

    def keyboard_return_results(self,event=None):
        if self.current_page=='聊天归档' and not self.busy and self.search_return_state:
            self.return_search_results();return 'break'

    def return_search_results(self):
        saved=self.search_return_state
        if not saved:return
        try:valid=saved['token']==self.controller.archive_view_token() and saved['query'][0]==self.owner_id
        except Exception:valid=False
        self.forget_search_return()
        if not valid:
            self.status.set('归档或身份已变化，旧搜索结果已撤销；请重新搜索。');return
        owner,peer,word,start,end=saved['query']
        self.peer_id=saved['peer_id'];self.search_scope.set('全部会话' if peer is None else '当前会话')
        self.notify_copilot_binding()
        self.search_word.set(word);self.start_date.set(start);self.end_date.set(end);self.contact_keyword.set(saved['contact_keyword'])
        self.contact_rows=saved['contact_rows']
        render=self.contact_tree.set_rows_incremental if self.background_browsing else self.contact_tree.set_rows
        render(self.contact_rows,self.peer_id);self.contact_count.set(f'{len(self.contact_rows)} 个')
        self.message_rows=saved['rows'];self.message_total=saved['total'];self.loaded_offset=saved['offset']
        self.loaded_query=saved['query'];self.loaded_token=saved['token'];self.browser_state='messages'
        self.chat_title.set(saved['title']);self.chat_subtitle.set(saved['subtitle'])
        if self.dates_expanded!=saved['dates_expanded']:self.toggle_dates()
        if self.background_browsing:
            self.chat_text.set_rows_incremental(self.message_rows,owner,word,peer is None,self.show_context)
            def restored():self.chat_text.pending_top=saved['top'];self.chat_text.restore_scroll()
            self.chat_text.after_render(restored)
        else:
            self.chat_text.set_rows(self.message_rows,owner,word,peer is None,self.show_context)
            self.chat_text.update_idletasks();region=self.chat_text.canvas.bbox('all')
            if region:self.chat_text.canvas.yview_moveto(saved['top']/max(1,region[3]))
        self.update_message_count(self.loaded_offset+len(self.message_rows)<self.message_total)
        self.conversation_export_button.configure(state='disabled' if peer is None else 'normal')
        self.ask_ai_button.configure(state='disabled' if self.peer_id is not None and self.peer_id<0 else 'normal')
        self.sync_management_messages();self.update_export_caption();self.remember_view()
        self.status.set('已返回搜索结果，筛选与阅读位置已恢复。')
