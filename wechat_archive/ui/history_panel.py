"""History is opened from one icon beside save and settings."""
import json
from datetime import datetime,timedelta,timezone
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from ..agent.history import ConversationHistory
from .slim_scrollbar import SlimScrollbar
from .search_entry import SearchEntry


def canonical(value):return json.loads(json.dumps(value,ensure_ascii=False))


class HistoryMixin:
    def initialize_history(self):
        self.history_store=ConversationHistory(self.app.controller.profile_dir)
        self.history_id=None;self.history_meta=None;self.history_job=None;self.history_viewing=False

    def queue_history(self):
        if not self.messages or self.history_viewing:return
        if not any(item['role'] in ('你','You') for item in self.messages):return
        if self.history_meta is None:
            try:
                scope=self.current_scope()
                self.history_meta={'scope':canonical(scope.key),'archive_token':canonical(self.app.controller.archive_view_token()),'archive_name':scope.path.name}
            except Exception:return
        if self.history_job:self.root.after_cancel(self.history_job)
        self.history_job=self.root.after(600,self.flush_history)

    def flush_history(self):
        if self.history_job:self.root.after_cancel(self.history_job)
        self.history_job=None
        if not self.messages or self.history_viewing or not self.history_meta:return
        title=next((x['text'] for x in self.messages if x['role'] in ('你','You')),'Codex 对话').replace('\n',' ')[:72]
        value={**self.history_meta,'id':self.history_id,'title':title,'thread_id':getattr(self.client,'thread_id',None) or self.history_meta.get('thread_id'),
               'messages':[dict(x) for x in self.messages],'model':self.model.get(),'effort':self.effort.get(),'complete':not self.active}
        try:
            saved=self.history_store.save(value);self.history_id=saved['id'];self.history_meta=saved
        except Exception as error:self.state.set('历史对话未能保存：'+str(error))

    def show_history(self):
        if self.active or self.busy:self.state.set('请先完成或停止当前回答，再查看历史。');return
        self.flush_history()
        old=getattr(self,'history_popup',None)
        if old and old.winfo_exists():old.destroy()
        popup=tk.Toplevel(self.root);self.history_popup=popup;popup.title('Codex · 历史对话');popup.geometry('760x540');popup.transient(self.root)
        body=ttk.Frame(popup,padding=16);body.pack(fill='both',expand=True);body.columnconfigure(0,weight=1);body.rowconfigure(2,weight=1)
        ttk.Label(body,text='历史对话',font=self.app.theme.title).grid(row=0,column=0,sticky='w',pady=(0,12))
        query=tk.StringVar(popup);search=ttk.Frame(body);search.grid(row=1,column=0,sticky='ew',pady=(0,12));search.columnconfigure(1,weight=1)
        ttk.Label(search,text='搜索历史',style='Hint.TLabel').grid(row=0,column=0,padx=(0,12));entry=SearchEntry(search,self.app.theme,query,'搜索历史对话…',lambda:fill());popup.search_entry=entry;entry.grid(row=0,column=1,sticky='ew')
        table=ttk.Frame(body);table.grid(row=2,column=0,sticky='nsew');table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        tree=ttk.Treeview(table,columns=('archive','time'),show='tree headings',selectmode='browse');tree.heading('#0',text='对话');tree.heading('archive',text='归档文件');tree.heading('time',text='更新时间（北京时间）');tree.column('#0',width=340);tree.column('archive',width=150);tree.column('time',width=190);tree.grid(row=0,column=0,sticky='nsew')
        scrollbar=SlimScrollbar(table,self.app.theme,command=tree.yview);scrollbar.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scrollbar.set);self.app.theme.wheel_router.register(tree,tree)
        footer=ttk.Frame(body);footer.grid(row=3,column=0,sticky='ew',pady=(12,0))
        hint=tk.StringVar(popup,value='历史保存在本机；选择后可离线查看。继续对话需要原归档及同一读取范围。')
        ttk.Label(body,textvariable=hint,style='Hint.TLabel',wraplength=700).grid(row=4,column=0,sticky='w',pady=(8,0))
        def fill(*_):
            tree.delete(*tree.get_children())
            for row in self.history_store.list(query.get()):
                stamp=datetime.fromisoformat(row['updated_at']).astimezone(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')
                tree.insert('','end',iid=row['id'],text=row['title'],values=(row.get('archive_name',''),stamp))
        def selected():
            ids=tree.selection()
            return self.history_store.read(ids[0]) if ids else None
        def view():
            row=selected()
            if not row:return
            window=tk.Toplevel(popup);window.title(row['title']);window.geometry('720x580')
            text=ScrolledText(window,wrap='word',font=self.app.theme.body);text.pack(fill='both',expand=True,padx=16,pady=16);self.app.theme.text_surface(text)
            text.insert('1.0','\n\n'.join(x['role']+'\n'+x['text'] for x in row['messages']));text.configure(state='disabled');self.app.theme.apply_tree(window)
        def resume():
            row=selected()
            if not row:return
            try:
                scope=self.current_scope()
                if row.get('scope')!=canonical(scope.key) or row.get('archive_token')!=canonical(self.app.controller.archive_view_token()):raise ValueError('当前归档、身份、会话或原文已变化；请选回原范围，或查看后新建对话。')
                if not self.client or not self.client.connected or not self.authenticated:raise ValueError('先在设置中连接并登录 Codex；离线查看不需要登录。')
                if not row.get('thread_id'):raise ValueError('该历史没有可继续的服务端线程；仍可离线查看原回答。')
                client=self.client;epoch=client.scope_epoch
                def done(_):
                    try:valid=client is self.client and row.get('scope')==canonical(self.current_scope().key) and row.get('archive_token')==canonical(self.app.controller.archive_view_token())
                    except Exception:valid=False
                    if not valid:
                        client.revoke_tools();hint.set('恢复期间归档或范围已变化，旧请求已撤销。');return
                    self.messages=[dict(x) for x in row['messages']];self.by_id={};self.history_id=row['id'];self.history_meta=row;self.history_viewing=False;self.last_scope=scope.key
                    self._render();self.state.set('历史对话已恢复，可继续提问。');popup.destroy()
                self.run(lambda:client.resume_conversation(row['thread_id'],scope,expected_epoch=epoch),done)
            except Exception as error:hint.set(str(error))
        ttk.Button(footer,text='查看',command=view).pack(side='left');ttk.Button(footer,text='继续对话',command=resume).pack(side='left',padx=8)
        def open_folder():
            self.history_store.path('0'*32);self.history_store.directory.mkdir(parents=True,exist_ok=True)
            __import__('os').startfile(str(self.history_store.directory))
        ttk.Button(footer,text='打开历史保存目录',command=open_folder).pack(side='right')
        tree.bind('<Double-1>',lambda _:view());query.trace_add('write',fill);popup.bind('<Escape>',lambda _:popup.destroy());fill();self.app.theme.apply_tree(popup);self.app.localizer.apply(popup,());entry.focus_set()
