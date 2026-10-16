"""Lazy offline help reader with chapters and search, available from the left sidebar."""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .help_content import CHAPTERS
from .theme import PAPER,INK,SELECTED
from .search_entry import SearchEntry


class HelpReader:
    def __init__(self,app,page):
        self.app=app;self.page=page;self.language=None;self.visible=[];u=app.theme.u
        app.title(page,'使用帮助')
        toolbar=ttk.Frame(page);toolbar.pack(fill='x',pady=(0,u(14)))
        ttk.Label(toolbar,text='搜索帮助').pack(side='left',padx=(0,u(10)))
        self.query=tk.StringVar(app.root);self.entry=SearchEntry(toolbar,app.theme,self.query,'搜索帮助内容…',self.filter)
        self.entry.pack(side='left',fill='x',expand=True)
        ttk.Button(toolbar,text='全部章节',command=lambda:self.query.set('')).pack(side='left',padx=u(10))
        body=ttk.Frame(page);body.pack(fill='both',expand=True)
        self.body=body
        self.chapters=tk.Listbox(body,width=23,font=app.theme.body,background=app.theme.color(PAPER),foreground=app.theme.color(INK),
            selectbackground=app.theme.color(SELECTED),selectforeground=app.theme.color(INK),activestyle='none',relief='flat',borderwidth=0,highlightthickness=0,exportselection=False)
        self.chapters.pack(side='left',fill='y',padx=(0,u(20)));self.chapters.bind('<<ListboxSelect>>',self.select)
        self.chapter_choice=ttk.Combobox(body,state='readonly',width=1)
        self.chapter_choice.bind('<<ComboboxSelected>>',self.choose_compact)
        self.text=ScrolledText(body,wrap='word',font=app.theme.body,width=1,state='disabled')
        app.theme.text_surface(self.text);self.text.pack(side='left',fill='both',expand=True)
        self.query.trace_add('write',lambda *_:self.filter());self.refresh_language()
        app.theme.wheel_router.register(self.chapters,self.chapters)
        app.theme.wheel_router.attach(page);app.theme.apply_tree(page)
        body.bind('<Configure>',self.layout,add='+')
        self.text.bind('<Configure>',lambda event:self.text.configure(padx=max(u(16),round((event.width-u(760))/2))) if event.widget is self.text else None,add='+')

    def layout(self,event=None):
        narrow=self.body.winfo_width()<self.app.theme.u(700)
        if narrow:
            if self.chapters.winfo_manager():self.chapters.pack_forget()
            if not self.chapter_choice.winfo_manager():self.chapter_choice.pack(side='top',fill='x',before=self.text,pady=(0,self.app.theme.u(12)))
        else:
            if self.chapter_choice.winfo_manager():self.chapter_choice.pack_forget()
            if not self.chapters.winfo_manager():self.chapters.pack(side='left',fill='y',before=self.text,padx=(0,self.app.theme.u(20)))

    def choose_compact(self,event=None):
        index=self.chapter_choice.current()
        if index>=0:self.chapters.selection_clear(0,'end');self.chapters.selection_set(index);self.select()

    def refresh_language(self):
        signature=(self.app.localizer.language,self.app.theme.body)
        if signature==self.language:return
        self.language=signature;self.filter()

    def filter(self):
        en=self.app.localizer.language=='en_US';q=self.query.get().casefold().strip()
        previous=self.visible[self.chapters.curselection()[0]] if self.chapters.curselection() and self.visible else None
        self.visible=[i for i,row in enumerate(CHAPTERS) if not q or q in (' '.join(row)).casefold()]
        self.chapters.delete(0,'end')
        short=('Getting started','Adding records','Search and copy','Export and files','AI connection','Appearance & shortcuts','Troubleshooting')
        labels=[CHAPTERS[i][1] if en else CHAPTERS[i][0] for i in self.visible]
        for value in labels:self.chapters.insert('end',value)
        self.chapter_choice.configure(values=labels)
        if self.visible:
            index=self.visible.index(previous) if previous in self.visible else 0
            self.chapters.selection_set(index);self.chapter_choice.current(index)
        self.select()

    def select(self,event=None):
        selection=self.chapters.curselection();en=self.app.localizer.language=='en_US'
        self.text.configure(state='normal');self.text.delete('1.0','end')
        if selection:
            row=CHAPTERS[self.visible[selection[0]]]
            self.text.insert('end',row[1 if en else 0]+'\n','heading')
            for paragraph in row[3 if en else 2].split('\n\n'):
                if paragraph.startswith('## '):
                    heading,_,content=paragraph.partition('\n');self.text.insert('end',heading[3:]+'\n','section')
                    if content:self.text.insert('end',content+'\n\n','paragraph')
                else:self.text.insert('end',paragraph+'\n\n','paragraph')
            self.text.tag_configure('heading',font=self.app.theme.title,spacing3=self.app.theme.u(6))
            self.text.tag_configure('section',font=self.app.theme.section,spacing1=self.app.theme.u(18),spacing3=self.app.theme.u(8))
            self.text.tag_configure('paragraph',spacing1=self.app.theme.u(2),spacing3=self.app.theme.u(8),spacing2=self.app.theme.u(3))
            q=self.query.get().strip()
            if q:
                start='1.0'
                while True:
                    index=self.text.search(q,start,stopindex='end',nocase=True)
                    if not index:break
                    start=f'{index}+{len(q)}c';self.text.tag_add('match',index,start)
                self.text.tag_configure('match',background=self.app.theme.color(SELECTED))
        else:self.text.insert('end','No matching chapters.' if en else '没有匹配章节。')
        self.text.configure(state='disabled');self.text.yview_moveto(0)
