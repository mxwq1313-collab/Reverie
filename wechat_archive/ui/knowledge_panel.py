"""本地知识问答：选择范围、建立索引、查证据、再生成；后台结果可撤销。"""

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from ..agent import ArchiveScope
from ..errors import ConflictError, ValidationError
from ..knowledge import KnowledgeSource
from ..knowledge.index import KnowledgeIndex
from ..knowledge.providers import LexicalEmbedding, OllamaEmbedding, OllamaEndpoint
from ..knowledge.rag import OllamaGenerator, RagService, answer_text
from ..knowledge.source import digest
from .common_widgets import Collapsible
from .message_widgets import display_time

OFFLINE = '离线字面检索（无需模型）'
OLLAMA = 'Ollama 语义检索（已有模型）'


class KnowledgePanel:
    def __init__(self, app, parent):
        self.app=app; self.root=app.root; self.parent=parent
        self.busy=False; self.running=0; self.closed=False; self.generation=0; self.events=queue.Queue()
        self.cancel_event=threading.Event(); self.hits=[]; self.answer=None; self.source=None; self.models=[]
        self.pending_request=None;self.failed_request=None
        u=app.theme.u
        saved=app.controller.settings().get('local_ai',{});saved=saved if isinstance(saved,dict) else {}
        self.preferred_kind=saved.get('kind',OFFLINE)
        from .workspace_widgets import card
        scope_host=card(parent,app.theme,'检索范围','从已归档原文里寻找证据。先选择范围，再更新索引。')
        row=ttk.Frame(scope_host); row.pack(fill='x',pady=u(5))
        self.scope=tk.StringVar(self.root,value='当前会话')
        ttk.Combobox(row,textvariable=self.scope,values=('当前会话','当前身份的所有私聊'),state='readonly',width=22).pack(side='left')
        self.kind=tk.StringVar(self.root,value=OFFLINE)
        config=getattr(app,'settings_ai_local',parent)
        ttk.Label(config,text='本地模型',font=app.theme.name).pack(anchor='w',pady=(0,u(8)))
        ttk.Combobox(config,textvariable=self.kind,values=(OFFLINE,OLLAMA),state='readonly',width=35).pack(anchor='w',pady=u(6))
        self.scope_text=tk.StringVar(self.root,value='先在聊天归档选择身份和会话')
        ttk.Label(scope_host,textvariable=self.scope_text,style='Hint.TLabel',wraplength=u(780)).pack(anchor='w',pady=u(5))
        self.advanced=Collapsible(config,'已有本地模型：服务地址与模型选择',app.theme); self.advanced.pack(fill='x',pady=u(5))
        self.endpoint=tk.StringVar(self.root,value=saved.get('endpoint') or 'http://127.0.0.1:11434')
        row=ttk.Frame(self.advanced.content); row.pack(fill='x',pady=u(4))
        ttk.Label(row,text='本机 Ollama',width=14).pack(side='left')
        ttk.Entry(row,textvariable=self.endpoint).pack(side='left',fill='x',expand=True)
        self.model_button=ttk.Button(row,text='读取已有模型',command=self.refresh_models); self.model_button.pack(side='left',padx=u(8))
        self.embedding_model=tk.StringVar(self.root,value=saved.get('embedding_model','')); self.chat_model=tk.StringVar(self.root,value=saved.get('chat_model',''))
        for label,var,attr in (('向量模型',self.embedding_model,'embedding_box'),('回答模型',self.chat_model,'chat_box')):
            row=ttk.Frame(self.advanced.content); row.pack(fill='x',pady=u(4))
            ttk.Label(row,text=label,width=14).pack(side='left')
            box=ttk.Combobox(row,textvariable=var,state='readonly'); box.pack(side='left',fill='x',expand=True); setattr(self,attr,box)
        ttk.Label(self.advanced.content,text='只读取已安装模型，不自动下载。请选择本地模型并检查服务配置；本地模型回答会把当前检索证据交给该服务。',style='Hint.TLabel',wraplength=u(750)).pack(anchor='w',pady=u(4))
        row=ttk.Frame(scope_host); row.pack(fill='x',pady=u(6))
        self.sync_button=ttk.Button(row,text='更新索引',command=self.sync); self.sync_button.pack(side='left')
        self.rebuild_button=ttk.Button(row,text='重新计算全部索引',command=lambda:self.sync(True)); self.rebuild_button.pack(side='left',padx=u(6))
        self.cancel_button=ttk.Button(row,text='取消',command=self.cancel); self.cancel_button.pack(side='left')
        self.state=tk.StringVar(self.root,value='离线字面检索可直接使用；先更新索引。')
        ttk.Label(scope_host,textvariable=self.state,style='Hint.TLabel',wraplength=u(780)).pack(anchor='w',pady=u(4))
        query_host=card(parent,app.theme,'你想找什么？','输入关键词或描述；Ctrl+Enter 检索。')
        self.input=ScrolledText(query_host,height=3,wrap='word',font=app.theme.body); self.input.pack(fill='x',pady=u(6))
        app.theme.text_surface(self.input,editable=True,framed=True)
        self.input.bind('<Control-Return>',self.shortcut); self.input.bind('<KeyRelease>',lambda _:self.controls())
        row=ttk.Frame(query_host); row.pack(fill='x')
        self.search_button=ttk.Button(row,text='检索原文',command=self.search,style='Primary.TButton'); self.search_button.pack(side='left')
        self.ask_button=ttk.Button(row,text='本地模型回答',command=self.ask); self.ask_button.pack(side='left',padx=u(7))
        results_host=card(parent,app.theme,'证据与原文','选择一条检索结果，核对原文后再使用。')
        result_actions=ttk.Frame(results_host);result_actions.pack(fill='x',pady=(0,u(8)))
        self.copy_button=ttk.Button(result_actions,text='复制回答与证据',command=self.copy); self.copy_button.pack(side='left')
        self.save_button=ttk.Button(result_actions,text='保存回答与证据',command=self.save); self.save_button.pack(side='left',padx=u(7))
        row=ttk.Frame(query_host);row.pack(fill='x',pady=u(4));self.recovery_row=row
        self.retry_button=ttk.Button(row,text='重试失败问题',command=self.retry);self.retry_button.pack(side='left')
        self.sync_retry_button=ttk.Button(row,text='更新索引并重试',command=self.sync_retry);self.sync_retry_button.pack(side='left',padx=u(7))
        table=ttk.Frame(results_host);table.pack(fill='x',pady=u(6));table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
        self.tree=ttk.Treeview(table,columns=('id','time','sender','score'),show='headings',height=4)
        for key,label,width in (('id','消息 ID',75),('time','北京时间',168),('sender','发送者',180),('score','检索相似度',100)):
            self.tree.heading(key,text=label); self.tree.column(key,width=u(width),stretch=key=='sender')
        self.tree.grid(row=0,column=0,sticky='nsew')
        from .slim_scrollbar import SlimScrollbar
        vertical=SlimScrollbar(table,app.theme,command=self.tree.yview);vertical.grid(row=0,column=1,sticky='ns')
        horizontal=SlimScrollbar(table,app.theme,command=self.tree.xview,orient='horizontal');horizontal.grid(row=1,column=0,sticky='ew')
        self.tree.configure(yscrollcommand=vertical.set,xscrollcommand=horizontal.set);app.theme.wheel_router.register(self.tree,self.tree)
        self.tree.bind('<<TreeviewSelect>>',lambda _:self.open_selected())
        self.output=ScrolledText(results_host,height=6,wrap='word',font=app.theme.body,state='disabled'); self.output.pack(fill='both',expand=True)
        app.theme.text_surface(self.output,background=app.theme.palette['CANVAS'])
        ttk.Label(parent,text='只覆盖所选范围已归档私聊文本。相似度不是置信度；模型推断需要核对原文。索引和保存文件包含聊天片段。',style='Hint.TLabel',wraplength=u(780)).pack(anchor='w',pady=u(5))
        for var in (self.scope,self.kind,self.endpoint,self.embedding_model,self.chat_model):
            var.trace_add('write',lambda *_:self.invalidate('范围或模型设置变化，请更新索引并重新检索。'))
        for var in (self.kind,self.endpoint,self.embedding_model,self.chat_model):var.trace_add('write',lambda *_:self.save_configuration())
        self.last_context=self.context(); self.controls(); self.poll_job=self.root.after(100 if self.busy else 500,self.poll)

    def save_configuration(self):
        settings=self.app.controller.settings()
        settings['local_ai']={'kind':self.kind.get(),'endpoint':self.endpoint.get(),'embedding_model':self.embedding_model.get(),'chat_model':self.chat_model.get()}
        self.app.controller.save_settings(settings)

    def current_scope(self):
        path=self.app.controller.require_archive(); owner=self.app.owner_id
        peer=self.app.peer_id if self.scope.get()=='当前会话' else None
        if owner is None or (self.scope.get()=='当前会话' and peer is None):
            raise ValidationError('请先在聊天归档选择身份和联系人。')
        if peer is not None and peer<0:raise ValidationError('本地语义检索目前支持私聊；请选择私聊会话，群聊可从聊天归档或 Codex 查看。')
        return ArchiveScope(path,owner,peer)

    def context(self):
        try:
            scope=self.current_scope()
            fingerprints=[]
            for path in (scope.path,Path(str(scope.path)+'-wal')):
                stat=path.stat() if path.exists() else None
                fingerprints.append((stat.st_ino,stat.st_size,stat.st_mtime_ns) if stat else None)
            return (scope.key,tuple(fingerprints),self.kind.get(),self.endpoint.get(),self.embedding_model.get(),self.chat_model.get())
        except (OSError,ValidationError): return None
        except Exception: return None

    def components(self):
        source=KnowledgeSource(self.current_scope())
        provider=LexicalEmbedding() if self.kind.get()==OFFLINE else OllamaEmbedding(OllamaEndpoint(self.endpoint.get()),self.embedding_model.get())
        # Model/processing-specific paths prevent one configuration from overwriting another's cache.
        name=digest([source.scope_id,source.processing,self.kind.get(),self.endpoint.get() if self.kind.get()==OLLAMA else '',self.embedding_model.get() if self.kind.get()==OLLAMA else ''])
        index=KnowledgeIndex(self.app.controller.data_dir/'knowledge_indexes'/f'{name}.db',source,provider)
        return source,index

    def controls(self):
        try: self.current_scope(); valid=True
        except Exception: valid=False
        text=bool(self.input.get('1.0','end').strip())
        for button,enabled in ((self.sync_button,valid),(self.rebuild_button,valid),(self.search_button,valid and text),
            (self.ask_button,valid and text and self.chat_model.get() in self.models),
            (self.copy_button,self.answer is not None),(self.save_button,self.answer is not None),(self.model_button,True)):
            disabled=not (enabled and not self.busy)
            if button.instate(['disabled'])!=disabled:button.state(['disabled'] if disabled else ['!disabled'])
        self.cancel_button.state(['!disabled'] if self.busy else ['disabled'])
        if self.chat_model.get() in self.models and self.kind.get()==OLLAMA:
            if not self.ask_button.winfo_manager():self.ask_button.pack(side='left',padx=self.app.theme.u(7))
        elif self.ask_button.winfo_manager():self.ask_button.pack_forget()
        retry_valid=self.failed_request is not None and self.failed_request['context']==self.context()
        if self.failed_request and not self.recovery_row.winfo_manager():self.recovery_row.pack(fill='x',pady=self.app.theme.u(4))
        elif not self.failed_request and self.recovery_row.winfo_manager():self.recovery_row.pack_forget()
        for button in (self.retry_button,self.sync_retry_button):button.state(['!disabled'] if retry_valid and not self.busy else ['disabled'])

    def write(self,text):
        self.output.configure(state='normal'); self.output.delete('1.0','end'); self.output.insert('end',text); self.output.configure(state='disabled')

    def invalidate(self,note):
        self.cancel_event.set(); self.generation+=1; self.busy=self.running>0
        self.hits=[]; self.answer=None; self.source=None
        self.failed_request=None;self.pending_request=None
        self.tree.delete(*self.tree.get_children()); self.write(''); self.state.set(note)
        self.last_context=self.context(); self.controls()

    def run(self,job,done,request=None):
        if self.busy: return
        token=self.context(); self.last_context=token
        self.cancel_event=threading.Event(); cancel=self.cancel_event; self.generation+=1; generation=self.generation
        self.running+=1; self.busy=True; self.controls()
        self.pending_request=request
        def progress(note): self.events.put((generation,token,'progress',note,None))
        def work():
            try:
                result=job(cancel.is_set,progress)
                self.events.put((generation,token,'done',result,done))
            except Exception as error:
                self.events.put((generation,token,'error',{'type':type(error).__name__,'message':str(error)},None))
        threading.Thread(target=work,daemon=True).start()

    def refresh_models(self):
        endpoint=self.endpoint.get()
        def done(rows):
            self.models=[r['name'] for r in rows]
            self.embedding_box['values']=self.models; self.chat_box['values']=self.models
            if self.preferred_kind==OLLAMA and self.embedding_model.get() in self.models:self.kind.set(OLLAMA)
            self.state.set(f'找到 {len(rows)} 个已有本地模型；请选择适合向量/回答的模型。')
            self.app.localize_ui()
        self.run(lambda *_:OllamaEndpoint(endpoint).models(),done)

    def sync(self,rebuild=False,retry_request=None):
        if self.busy:return
        try: source,index=self.components()
        except Exception as error: self.state.set(str(error)); return
        self.answer=None; self.hits=[]; self.tree.delete(*self.tree.get_children()); self.write('')
        def done(result):
            self.source=source
            self.state.set(f"索引已更新：{result['messages']} 条消息 / {result['chunks']} 个片段，新增计算 {result['embedded']}，复用 {result['reused']}，移除 {result['deleted']}。")
            if retry_request:self.root.after(0,lambda:self.repeat_request(retry_request))
        self.run(lambda cancel,progress:index.sync(cancel,progress,rebuild),done)

    def search(self):
        if self.busy:return
        try: source,index=self.components(); query=self.input.get('1.0','end').strip()
        except Exception as error: self.state.set(str(error)); return
        self.answer=None
        def done(result):
            self.source=source; self.show_hits(result['hits'])
            self.write('找到 '+str(len(self.hits))+' 个原文片段。点击列表回查原文。' if self.hits else '当前范围没有达到阈值的片段。可改用原词检索。')
            self.state.set('检索完成 · '+('离线字面向量' if result['embedding']['kind']=='lexical' else '本地模型语义向量'))
        self.failed_request=None;self.state.set('正在检索原文…')
        self.run(lambda *_:index.search(query),done,{'action':'search','query':query,'context':self.context()})

    def ask(self):
        if self.busy:return
        try:
            if self.chat_model.get() not in self.models: raise ValidationError('先读取已有模型并选择回答模型。')
            source,index=self.components(); query=self.input.get('1.0','end').strip()
            generator=OllamaGenerator(OllamaEndpoint(self.endpoint.get()),self.chat_model.get())
        except Exception as error: self.state.set(str(error)); return
        self.answer=None
        def done(result):
            self.source=source; self.answer=result
            self.show_hits([{'chunk':e['chunk'],'score':e['score']} for e in result['evidence']])
            self.write(answer_text(result)); self.state.set('问答完成 · '+result['notice'])
        self.failed_request=None;self.state.set('正在检索证据并等待本地模型；完成后校验引用…')
        self.run(lambda cancel,_:RagService(index,generator).ask(query,cancel=cancel),done,{'action':'ask','query':query,'context':self.context()})

    def repeat_request(self,request):
        if self.busy:return
        if request['context']!=self.context():self.invalidate('归档、范围或模型已变化，请重新提问。');return
        self.input.delete('1.0','end');self.input.insert('1.0',request['query'])
        if request['action']=='ask':self.ask()
        else:self.search()

    def retry(self):
        if self.failed_request:self.repeat_request(dict(self.failed_request))

    def sync_retry(self):
        if self.failed_request and self.failed_request['context']==self.context():self.sync(retry_request=dict(self.failed_request))

    def show_hits(self,hits):
        self.hits=hits; self.tree.delete(*self.tree.get_children())
        for i,hit in enumerate(hits):
            c=hit['chunk']; self.tree.insert('', 'end',iid=str(i),values=(c['reference']['message']['message_id'],display_time(c['timestamp_utc']).strftime('%Y-%m-%d %H:%M'),c['sender_name'],hit['score']))

    def open_selected(self):
        selected=self.tree.selection()
        if not selected or self.source is None: return
        try:
            if self.context()!=self.last_context: raise ConflictError('范围或归档变化，原文引用已撤销。')
            index=int(selected[0]); chunk=self.source.resolve(self.hits[index]['chunk']['reference']).to_dict()
            text=f"原文 · 消息 #{chunk['reference']['message']['message_id']} · {chunk['timestamp_utc']}\n{chunk['sender_name']} → {chunk['receiver_name']}\n字符 {chunk['reference']['start']}–{chunk['reference']['end']}\n\n{chunk['text']}"
            if self.answer:
                text+='\n\n'+answer_text(self.answer)
            self.write(text)
        except Exception as error: self.invalidate(str(error))

    def checked_answer(self):
        if self.answer is None or self.source is None: raise ValidationError('没有可保存的已核验回答。')
        if self.context()!=self.last_context: raise ConflictError('范围或原文已变化，请重新问答。')
        for evidence in self.answer['evidence']:
            if self.source.resolve(evidence['chunk']['reference']).to_dict()!=evidence['chunk']:
                raise ConflictError('证据已变化，请重新问答。')
        return answer_text(self.answer)

    def copy(self):
        try:
            text=self.checked_answer(); self.root.clipboard_clear(); self.root.clipboard_append(text); self.state.set('已复制回答和原文证据。')
        except Exception as error: self.invalidate(str(error))

    def save(self):
        try:
            text=self.checked_answer()
            path=filedialog.asksaveasfilename(parent=self.root,title='保存到新文件',initialfile='本地知识回答.txt',defaultextension='.txt')
            if not path: return
            # Recheck after a modal dialog in case scope changed while it was open.
            text=self.checked_answer()
            with Path(path).open('x',encoding='utf-8') as output: output.write(text)
            self.state.set('回答和证据已保存到新文件。')
        except Exception as error: self.state.set('保存未完成：'+str(error))

    def cancel(self): self.invalidate('操作已取消；正在进行的本地模型请求返回后会丢弃结果。')
    def shortcut(self,event=None): self.search(); return 'break'

    def poll(self):
        if self.closed: return
        current=self.context()
        if current!=self.last_context: self.invalidate('范围或原文已变化，结果已清除；请更新索引。')
        try:
            while True:
                generation,token,kind,result,done=self.events.get_nowait()
                if kind in ('done','error','retired'):
                    self.running=max(0,self.running-1); self.busy=self.running>0
                    if kind=='retired':continue
                if generation!=self.generation or token!=self.context(): continue
                if kind=='progress': self.state.set(result)
                else:
                    if kind=='error':
                        self.failed_request=self.pending_request
                        hint='可重试失败问题。'
                        if result['type']=='ConflictError':hint='索引或原文状态已变化；可更新索引后重试。'
                        elif any(word in result['message'] for word in ('连接','服务','超时')):hint='请检查本地模型服务，再重试原问题。'
                        self.state.set('未完成：'+result['message']+'；'+hint)
                    else:
                        self.failed_request=None;done(result)
                    self.pending_request=None
        except queue.Empty: pass
        try:
            scope=self.current_scope(); names={u['id']:u['nickname'] for u in self.app.archive_users}
            peer=names.get(scope.peer_id,'联系人') if scope.peer_id else '全部已归档私聊'
            self.scope_text.set(f"{names.get(scope.user_id,'身份')} ↔ {peer}")
        except Exception as error: self.scope_text.set(str(error) or '先在聊天归档选择身份和会话')
        self.controls(); self.poll_job=self.root.after(100 if self.busy else 500,self.poll)

    def close(self):
        if self.closed: return
        self.closed=True; self.cancel_event.set(); self.generation+=1
        self.root.after_cancel(self.poll_job)
