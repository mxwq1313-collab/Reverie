"""Independent local utilities with explicit scope, pagination and reversible editing."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import random, re
import tkinter as tk
from tkinter import ttk, filedialog
from tkinter.scrolledtext import ScrolledText
from .workspace_widgets import card, ActionRow
from .slim_scrollbar import SlimScrollbar

ZONE = timezone(timedelta(hours=8))


class ToolboxPanel:
    def __init__(self, app):
        self.app=app;self.row=None;self.bound=None;self.views={};self.active=None
        self.capsule=MemoryTool(self,'时光胶囊','date');self.random=MemoryTool(self,'随机回忆','random')
        self.date=self.capsule.start
        self.memory=self.capsule.memory;self.scope=self.capsule.scope

    def frame(self,name,hint):
        app=self.app
        parent=app.capsule_content if name=='时光胶囊' else app.pages[name]
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True);self.views[name]=frame
        if name=='随机回忆':return frame
        ttk.Label(frame,text=name,font=app.theme.section).pack(anchor='w',pady=(0,app.theme.u(8)))
        ttk.Label(frame,text=hint,style='Hint.TLabel',wraplength=app.theme.u(450)).pack(anchor='w',pady=(0,app.theme.u(8)))
        return frame

    def activate(self,name):
        if name not in self.views:name=None
        if name==getattr(self,'visible_view',False):return
        for key,frame in self.views.items():
            frame.pack_forget()
        self.visible_view=name;self.active=name
        if name is not None:
            frame=self.views[name];frame.pack(fill='both',expand=True);self.app.theme.apply_tree(frame)
            if name=='随机回忆':self.random.refresh_context()

    def open_tool(self,name,navigate=True):
        if name not in self.views:raise ValueError('未知工具')
        if navigate:self.app.show_page(name)
        else:self.activate(name)

    def binding(self):
        app=self.app
        return str(app.controller.database),app.owner_id,app.peer_id,app.controller.archive_view_token()
    def read(self,mode):
        tool=self.capsule if mode=='date' else self.random;self.open_tool(tool.name);tool.search()
    def adopt(self,tool):self.row=tool.row;self.bound=tool.bound;self.memory=tool.memory;self.scope=tool.scope
    def valid_memory(self):return (self.capsule if self.memory is self.capsule.memory else self.random).valid()
    def open_original(self):(self.capsule if self.memory is self.capsule.memory else self.random).open_original()
    def copy_memory(self):(self.capsule if self.memory is self.capsule.memory else self.random).copy()


class MemoryTool:
    def __init__(self, box, name, mode):
        self.box=box;self.app=app=box.app;self.name=name;self.mode=mode
        self.row=None;self.bound=None;self.items=[];self.offset=0;self.total=0
        self.history=[];self.cursor=-1;self.seen=[];self.history_key=None
        page=box.frame(name,'沿用聊天归档中当前选择的身份与会话。');u=app.theme.u
        if mode=='random':
            self.build_random(page);return
        self.scope=tk.StringVar(page,value='先在聊天归档选择会话，再开始探索。')
        ttk.Label(page,textvariable=self.scope,style='Hint.TLabel',wraplength=u(450)).pack(anchor='w',pady=(0,u(12)))
        filters=ttk.Frame(page);filters.pack(fill='x',pady=(0,u(8)))
        ttk.Label(filters,text='北京时间 · 包含起止日 · '+('只填开始日期表示当天' if mode=='date' else '留空表示不限制'),style='Hint.TLabel',wraplength=u(450)).pack(anchor='w',pady=(0,u(6)))
        self.start=tk.StringVar(page,value=datetime.now(ZONE).strftime('%Y-%m-%d') if mode=='date' else '')
        self.end=tk.StringVar(page);self.keyword=tk.StringVar(page)
        fields=ttk.Frame(filters);fields.pack(fill='x');fields.columnconfigure(1,weight=1);fields.columnconfigure(3,weight=1)
        for column,label,var in ((0,'从',self.start),(2,'至',self.end)):
            ttk.Label(fields,text=label).grid(row=0,column=column,padx=(0,u(7)),sticky='w')
            ttk.Entry(fields,textvariable=var,width=12).grid(row=0,column=column+1,sticky='ew',padx=(0,u(12)))
        ttk.Label(fields,text='关键词').grid(row=1,column=0,sticky='w',pady=u(8))
        entry=ttk.Entry(fields,textvariable=self.keyword);entry.grid(row=1,column=1,columnspan=3,sticky='ew',pady=u(8));entry.bind('<Return>',lambda _:self.search())
        actions=ActionRow(filters,app.theme)
        self.search_button=app.button(actions,'打开时光胶囊' if mode=='date' else '打捞一条回忆',self.search,True);actions.add(self.search_button)
        if mode=='date':
            for label,amount in (('前一天',-1),('后一天',1)):actions.add(app.button(actions,label,lambda delta=amount:self.shift(delta)))
        else:
            actions.add(app.button(actions,'上一条',lambda:self.visit(-1)));actions.add(app.button(actions,'下一条',lambda:self.visit(1)))
            actions.add(app.button(actions,'清空回看记录',self.clear_history))
        self.summary=tk.StringVar(page,value='尚未读取')
        ttk.Label(page,textvariable=self.summary,style='Hint.TLabel').pack(anchor='w',pady=(u(8),u(5)))
        if mode=='date':
            table_frame=ttk.Frame(page);table_frame.pack(fill='x')
            self.tree=ttk.Treeview(table_frame,columns=('time','sender'),show='headings',height=3,selectmode='browse')
            self.tree.heading('time',text='北京时间');self.tree.heading('sender',text='发送者')
            self.tree.column('time',width=u(165));self.tree.column('sender',width=u(220))
            bar=SlimScrollbar(table_frame,app.theme,command=self.tree.yview);self.tree.configure(yscrollcommand=bar.set)
            self.tree.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
            self.tree.bind('<<TreeviewSelect>>',self.select);self.tree.bind('<Double-1>',lambda _:self.open_original())
            app.theme.wheel_router.register(self.tree,self.tree)
            pages=ActionRow(page,app.theme);self.previous=app.button(pages,'上一页',lambda:self.search(self.offset-100));pages.add(self.previous)
            self.next=app.button(pages,'下一页',lambda:self.search(self.offset+100));pages.add(self.next)
            self.previous.configure(state='disabled');self.next.configure(state='disabled')
        self.memory=ScrolledText(page,height=4,wrap='word',font=app.theme.body,state='disabled')
        app.theme.text_surface(self.memory,background=app.theme.palette['CANVAS']);self.memory.pack(fill='both',expand=True,pady=u(10))
        footer=ActionRow(page,app.theme)
        for label,command in (('回到原文',self.open_original),('复制这条回忆',self.copy),('保存这条回忆',self.save)):
            footer.add(app.button(footer,label,command))
        if mode=='date':footer.add(app.button(footer,'保存当前页',lambda:self.save(page=True)))

    def build_random(self,page):
        app=self.app;u=app.theme.u
        header=ttk.Frame(page);header.pack(fill='x',pady=(0,u(10)))
        ttk.Label(header,text='随机回忆',font=app.theme.section).pack(anchor='w')
        ttk.Label(header,text='从旧对话里，遇见一个片刻。',style='Hint.TLabel').pack(anchor='w',pady=(u(4),0))
        self.scope=tk.StringVar(page,value='先在聊天归档中选择一个会话')
        self.scope_label=ttk.Label(page,textvariable=self.scope,style='Hint.TLabel',wraplength=u(450))
        self.scope_label.pack(fill='x',pady=(0,u(12)))
        controls=ActionRow(page,app.theme)
        self.search_button=controls.add(app.button(controls,'打捞一条回忆',self.search,True))
        self.filter_button=controls.add(app.button(controls,'筛选条件 ▾',self.toggle_filters))
        self.start=tk.StringVar(page);self.end=tk.StringVar(page);self.keyword=tk.StringVar(page)
        self.filters=ttk.Frame(page,padding=(0,u(8),0,u(4)))
        self.filters.columnconfigure(0,weight=1);self.filters.columnconfigure(1,weight=1)
        for column,label,var in ((0,'开始日期',self.start),(1,'结束日期',self.end)):
            ttk.Label(self.filters,text=label,style='Hint.TLabel').grid(row=0,column=column,sticky='w')
            entry=ttk.Entry(self.filters,textvariable=var,width=12)
            entry.grid(row=1,column=column,sticky='ew',padx=(0,u(8)) if column==0 else 0,pady=(u(4),u(8)))
            entry.bind('<Return>',lambda _:self.search())
        ttk.Label(self.filters,text='关键词',style='Hint.TLabel').grid(row=2,column=0,sticky='w')
        entry=ttk.Entry(self.filters,textvariable=self.keyword,width=12)
        entry.grid(row=3,column=0,columnspan=2,sticky='ew',pady=(u(4),u(4)));entry.bind('<Return>',lambda _:self.search())
        ttk.Label(self.filters,text='日期格式 YYYY-MM-DD · 北京时间 · 留空不限',style='Hint.TLabel',wraplength=u(400)).grid(row=4,column=0,columnspan=2,sticky='w')
        self.summary=tk.StringVar(page,value='回忆只从当前会话中打捞')
        self.summary_label=ttk.Label(page,textvariable=self.summary,style='Hint.TLabel',wraplength=u(450))
        self.summary_label.pack(fill='x',pady=(u(10),u(8)))
        self.memory=ScrolledText(page,width=1,height=8,wrap='word',font=app.theme.body,state='disabled')
        app.theme.text_surface(self.memory,background=app.theme.palette['CANVAS'])
        self.memory.pack(fill='both',expand=True,pady=(0,u(8)))
        history=ActionRow(page,app.theme)
        self.previous=history.add(app.button(history,'上一条',lambda:self.visit(-1)))
        self.next=history.add(app.button(history,'下一条',lambda:self.visit(1)))
        self.clear_button=history.add(app.button(history,'清空回看',self.clear_history))
        footer=ActionRow(page,app.theme);self.result_buttons=[]
        for label,command in (('回到原文',self.open_original),('复制',self.copy),('保存',self.save)):
            self.result_buttons.append(footer.add(app.button(footer,label,command)))
        footer.pack_configure(side='bottom',before=header)
        history.pack_configure(side='bottom',before=header)
        self.memory.configure(state='normal');self.memory.insert('1.0','让一段旧对话，偶然出现。\n\n点击“打捞一条回忆”开始。');self.memory.configure(state='disabled')
        def fit(event):
            if event.widget is page:
                width=max(u(100),event.width)
                self.scope_label.configure(wraplength=width);self.summary_label.configure(wraplength=width)
        page.bind('<Configure>',fit,add='+');self.update_controls()

    def toggle_filters(self):
        if self.filters.winfo_manager():self.filters.pack_forget()
        else:self.filters.pack(fill='x',before=self.summary_label)
        self.filter_button.configure(text='收起筛选 ▴' if self.filters.winfo_manager() else '筛选条件 ▾')

    def update_controls(self):
        if self.mode!='random':return
        for button,enabled in ((self.previous,self.row is not None and self.cursor>0),(self.next,self.row is not None and self.cursor+1<len(self.history)),(self.clear_button,bool(self.history))):
            button.configure(state='normal' if enabled else 'disabled')
        for button in self.result_buttons:button.configure(state='normal' if self.row is not None else 'disabled')

    def refresh_context(self):
        if self.mode!='random':return
        binding=self.box.binding()
        if self.bound is not None and binding!=self.bound:self.clear_history(quiet=True);self.display(None);self.summary.set('会话已变化，重新打捞一条回忆')
        names={x['id']:x['nickname'] for x in (*self.app.archive_users,*self.app.contact_rows)}
        if self.app.owner_id is not None and self.app.peer_id is not None:self.scope.set(names.get(self.app.owner_id,'当前身份')+' ↔ '+names.get(self.app.peer_id,'当前会话'))
        else:self.scope.set('先在聊天归档中选择一个会话')

    def query(self):
        app=self.app;app.controller.require_archive()
        if app.owner_id is None:raise ValueError('请先在聊天归档选择身份。')
        if app.peer_id is None:raise ValueError('请先在聊天归档选择会话。')
        start=self.start.get().strip();end=self.end.get().strip()
        for value in (start,end):
            try:
                if value:datetime.strptime(value,'%Y-%m-%d')
            except ValueError:raise ValueError('日期请填写 YYYY-MM-DD，例如 2026-10-16。') from None
        if start and end and start>end:raise ValueError('开始日期不能晚于结束日期。')
        if self.mode=='date' and not end:end=start
        return self.box.binding(),(app.owner_id,app.peer_id,self.keyword.get().strip() or None,start or None,end or None)

    def search(self, offset=0):
        app=self.app
        if app.busy:return
        try:binding,args=self.query()
        except Exception as error:
            app.status.set(str(error))
            if self.mode=='random':self.summary.set(str(error))
            return
        key=(binding,args)
        if self.mode=='random' and key!=self.history_key:self.clear_history(quiet=True);self.display(None);self.history_key=key
        if self.mode=='date' and args!=getattr(self,'last_args',None):offset=0
        self.last_args=args
        reader=app.controller.read_snapshot(None);seen=tuple(self.seen);offset=max(0,offset)
        def work():
            if self.mode=='date':return reader.messages(*args,offset=offset),None
            first=reader.messages(*args);total=first['total'];excluded={x for x in seen if x<total}
            if not total:return first,None
            if len(excluded)==total:return {'items':[],'total':total,'exhausted':True},None
            target=random.randrange(total-len(excluded))
            for used in sorted(excluded):
                if used<=target:target+=1
            return reader.messages(*args,offset=target),target
        def done(result):
            if binding!=self.box.binding():
                app.status.set('范围已变化，本次回忆已撤销。')
                if self.mode=='random':self.refresh_context();self.summary.set('会话已变化，重新打捞一条回忆')
                return
            page,chosen=result
            if page.get('exhausted'):
                message='当前条件下的回忆已全部打捞，可清空回看记录后重试。'
                app.status.set(message)
                if self.mode=='random':self.summary.set(message)
                return
            self.bound=binding;self.total=page['total'];self.items=page['items'];self.offset=page.get('offset',offset)
            names={x['id']:x['nickname'] for x in (*app.archive_users,*app.contact_rows)}
            self.scope.set(names.get(args[0],'当前身份')+' ↔ '+names.get(args[1],'当前会话'))
            if self.mode=='date':
                self.tree.delete(*self.tree.get_children())
                for row in self.items:self.tree.insert('', 'end',iid=str(row['id']),values=(self.stamp(row),row['sender_name']))
                self.previous.configure(state='normal' if self.offset>0 else 'disabled')
                self.next.configure(state='normal' if self.offset+len(self.items)<self.total else 'disabled')
                self.summary.set(f"共 {self.total:,} 条 · 当前 {self.offset+1 if self.items else 0}–{self.offset+len(self.items)} 条")
                if self.items:self.tree.selection_set(str(self.items[0]['id']))
            elif self.items:
                self.history=self.history[:self.cursor+1];self.history.append(self.items[0]);self.history=self.history[-100:];self.cursor=len(self.history)-1
                self.seen.append(chosen);self.seen=self.seen[-100:]
                self.summary.set(f'从 {self.total:,} 条中打捞 · 回看 {self.cursor+1}/{len(self.history)} · 最近100条避免重复')
            if self.mode=='random' and not self.items:self.summary.set('没有匹配记录，试试其他筛选条件')
            self.display(self.items[0] if self.items else None)
            app.status.set('已打开归档回忆。' if self.items else '当前条件没有已归档记录。')
        if self.mode=='random':self.summary.set('正在打捞这段对话里的回忆…')
        app.run('正在寻找所选会话中的回忆…',work,done)

    @staticmethod
    def stamp(row):return datetime.fromisoformat(row['create_time'].replace('Z','+00:00')).astimezone(ZONE).strftime('%Y-%m-%d %H:%M:%S')
    def formatted(self,row):
        from .media_widgets import present_content
        return f"{self.stamp(row)} · {row['sender_name']}\n\n{present_content(row)}\n\n[消息 #{row['id']}]"
    def display(self,row):
        self.row=row;self.memory.configure(state='normal');self.memory.delete('1.0','end');self.memory.insert('1.0',self.formatted(row) if row else ('暂时没有回忆。\n可以更换筛选条件，再打捞一次。' if self.mode=='random' else '当前日期或条件下没有已归档记录。'));self.memory.configure(state='disabled');self.box.adopt(self);self.update_controls()
    def select(self,event=None):
        choice=self.tree.selection()
        if choice:
            row=next((x for x in self.items if str(x['id'])==choice[0]),None)
            if row:self.display(row)
    def valid(self):
        try:valid=self.row is not None and self.bound==self.box.binding()
        except Exception:valid=False
        if not valid:self.app.status.set('请先在当前范围打捞一条回忆。');return False
        return True
    def open_original(self):
        if self.valid():self.app.show_page('聊天归档');self.app.show_context(self.row['id']);self.app.status.set('已回到回忆对应的原文。')
    def copy(self):
        if self.valid():self.app.root.clipboard_clear();self.app.root.clipboard_append(self.formatted(self.row));self.app.status.set('回忆与消息编号已复制。')
    def save(self,page=False):
        if not self.valid():return
        path=filedialog.asksaveasfilename(parent=self.app.root,title='保存回忆',defaultextension='.txt',filetypes=[('UTF-8文本','*.txt')])
        if not path:return
        value='\n\n'+'─'*24+'\n\n'
        try:Path(path).write_text(value.join(self.formatted(x) for x in self.items) if page else self.formatted(self.row),encoding='utf-8');self.app.status.set('回忆已保存为UTF-8文本。')
        except OSError as error:self.app.status.set('保存未完成：'+str(error))
    def shift(self,days):
        try:value=datetime.strptime(self.start.get(),'%Y-%m-%d')+timedelta(days=days)
        except ValueError:self.app.status.set('日期请填写 YYYY-MM-DD。');return
        self.start.set(value.strftime('%Y-%m-%d'));self.end.set('');self.search()
    def visit(self,step):
        if not self.valid():return
        target=self.cursor+step
        if not 0<=target<len(self.history):self.app.status.set('已到回看记录边界；可继续打捞新回忆。');return
        self.cursor=target;self.display(self.history[target]);self.summary.set(f'回看 {target+1}/{len(self.history)} · 当前条件共 {self.total:,} 条')
    def clear_history(self,quiet=False):
        self.history=[];self.seen=[];self.cursor=-1;self.row=None;self.bound=None
        self.update_controls()
        if not quiet:self.display(None);self.summary.set('回看记录已清空');self.app.status.set('已清空本工具中的回看记录。')
