"""Searchable scope selection, committed only by Apply."""
import tkinter as tk
from tkinter import ttk
from .slim_scrollbar import SlimScrollbar
from .search_entry import SearchEntry


def open_scope_picker(panel):
    app=panel.app
    if app.busy:return
    old=getattr(panel,'scope_popup',None)
    if old and old.winfo_exists():old.lift();return
    popup=tk.Toplevel(panel.root);panel.scope_popup=popup;popup.title('选择读取范围');popup.geometry('650x560');popup.transient(panel.root)
    body=ttk.Frame(popup,padding=20);body.pack(fill='both',expand=True);body.columnconfigure(0,weight=1);body.rowconfigure(5,weight=1)
    ttk.Label(body,text='选择归档与会话',font=app.theme.title).grid(row=0,column=0,sticky='w')
    bar=ttk.Frame(body);bar.grid(row=1,column=0,sticky='ew',pady=(12,16));bar.columnconfigure(0,weight=1)
    ttk.Label(bar,text=str(app.controller.database or '未打开归档'),style='Hint.TLabel',wraplength=480).grid(row=0,column=0,sticky='w')
    app.icon(bar,'folder','打开归档',lambda:(popup.destroy(),app.open_archive())).grid(row=0,column=1)
    owners=ttk.Combobox(body,state='readonly',values=[x['nickname']+' · '+str(x['id']) for x in app.archive_users]);owners._raw_values=True;owners.grid(row=2,column=0,sticky='ew')
    mode=tk.StringVar(popup,value=panel.scope.get());modes=ttk.Frame(body);modes.grid(row=3,column=0,sticky='ew',pady=(12,8))
    ttk.Radiobutton(modes,text='当前会话',variable=mode,value='当前会话').pack(side='left');ttk.Radiobutton(modes,text='当前身份的所有私聊',variable=mode,value='当前身份的所有私聊').pack(side='left',padx=16)
    query=tk.StringVar(popup);search=ttk.Frame(body);search.grid(row=4,column=0,sticky='ew',pady=(0,8));search.columnconfigure(1,weight=1)
    ttk.Label(search,text='搜索会话',style='Hint.TLabel').grid(row=0,column=0,padx=(0,12));entry=SearchEntry(search,app.theme,query,'搜索会话…',lambda:fill());popup.search_entry=entry;entry.grid(row=0,column=1,sticky='ew')
    table=ttk.Frame(body);table.grid(row=5,column=0,sticky='nsew');table.columnconfigure(0,weight=1);table.rowconfigure(0,weight=1)
    tree=ttk.Treeview(table,columns=('count','own'),show='tree headings',selectmode='browse');tree.heading('#0',text='会话');tree.heading('count',text='消息数');tree.heading('own',text='本人占比');tree.column('#0',width=330);tree.column('count',width=90);tree.column('own',width=90);tree.grid(row=0,column=0,sticky='nsew')
    scrollbar=SlimScrollbar(table,app.theme,command=tree.yview);scrollbar.grid(row=0,column=1,sticky='ns');tree.configure(yscrollcommand=scrollbar.set);app.theme.wheel_router.register(tree,tree)
    hint=tk.StringVar(popup,value='仅把所选会话范围交给 Codex 的只读工具；附件原文件不会自动上传。')
    ttk.Label(body,textvariable=hint,style='Hint.TLabel',wraplength=580).grid(row=6,column=0,sticky='w',pady=12)
    rows=[]
    def fill(*_):
        nonlocal rows
        tree.delete(*tree.get_children());index=owners.current()
        if index<0:return
        owner=app.archive_users[index]['id'];rows=[x for x in app.controller.contacts(owner,query.get() or None) if x['message_count']>0]
        for item in rows:tree.insert('','end',iid=str(item['id']),text=item['nickname'],values=(item['message_count'],f"{item.get('own_ratio',0):.1%}"))
        if str(app.peer_id) in tree.get_children():tree.selection_set(str(app.peer_id));tree.see(str(app.peer_id))
    def apply():
        index=owners.current();chosen=tree.selection()
        if index<0 or mode.get()=='当前会话' and not chosen:hint.set('请选择身份与会话');return
        if app.owner_box.current()!=index:app.owner_box.current(index);app.change_owner()
        if chosen:app.peer_id=int(chosen[0]);app.contact_tree.selection_set(chosen[0]);app.load_messages();app.remember_view()
        panel.scope.set(mode.get());app.notify_copilot_binding();popup.destroy()
    footer=ttk.Frame(body);footer.grid(row=7,column=0,sticky='ew');ttk.Button(footer,text='取消',command=popup.destroy).pack(side='right');ttk.Button(footer,text='应用范围',command=apply,style='Primary.TButton').pack(side='right',padx=8)
    ids=[x['id'] for x in app.archive_users]
    if app.owner_id in ids:owners.current(ids.index(app.owner_id))
    owners.bind('<<ComboboxSelected>>',fill);query.trace_add('write',fill);tree.bind('<Double-1>',lambda _:apply());popup.bind('<Escape>',lambda _:popup.destroy());fill();app.theme.apply_tree(popup);app.localizer.apply(popup,());entry.focus_set()
