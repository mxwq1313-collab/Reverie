"""可折叠设置、可滚动面板和真实结果摘要。"""
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from .theme import CANVAS,PAPER,INK,SECONDARY
from .slim_scrollbar import SlimScrollbar


class Collapsible(ttk.Frame):
    def __init__(self,parent,label,theme):
        super().__init__(parent)
        self.label=label;self.expanded=False;self.theme=theme
        self.button=ttk.Button(self,text='▸ '+label,command=self.toggle,style='Disclosure.TButton')
        self.button.pack(fill='x',pady=(theme.u(3),theme.u(3)))
        self.content=ttk.Frame(self,padding=(theme.u(8),0))

    def toggle(self):self.set_expanded(not self.expanded)
    def set_expanded(self,value):
        self.expanded=bool(value);self.button.configure(text=('▾ ' if value else '▸ ')+self.label)
        if value:self.content.pack(fill='both',expand=True);self.theme.wheel_router.attach_later(self.content)
        else:self.content.pack_forget()


class ScrollPanel(ttk.Frame):
    def __init__(self,parent,theme):
        super().__init__(parent)
        self.canvas=tk.Canvas(self,background=PAPER,highlightthickness=0)
        scrollbar=SlimScrollbar(self,theme,command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side='left',fill='both',expand=True);scrollbar.pack(side='right',fill='y')
        self.body=ttk.Frame(self.canvas,padding=theme.u(20))
        self.window_id=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(self.window_id,width=e.width))
        theme.wheel_router.register(self,self.canvas,canvas=True)


class ResultCard(ttk.Frame):
    def __init__(self,parent,theme,label='查看详细结果'):
        super().__init__(parent,padding=(0,theme.u(10)))
        self.theme=theme
        self.state=tk.StringVar(self,value='尚未执行')
        ttk.Label(self,textvariable=self.state,style='Hint.TLabel').pack(anchor='w')
        row=ttk.Frame(self);row.pack(fill='x',pady=theme.u(10))
        self.values=[];self.labels=[]
        for index,caption in enumerate(('新增消息','重复跳过','失败记录','未支持但已保留')):
            block=ttk.Frame(row);block.grid(row=0,column=index,sticky='nsew',padx=(0,theme.u(26)));row.columnconfigure(index,weight=1)
            value=tk.StringVar(self,value='—');count_label=tk.StringVar(self,value=caption)
            ttk.Label(block,textvariable=value,font=theme.title).pack(anchor='w')
            ttk.Label(block,textvariable=count_label,style='Hint.TLabel').pack(anchor='w')
            self.values.append(value);self.labels.append(count_label)
        self.expander=Collapsible(self,label,theme);self.expander.pack(fill='both',expand=True)
        self.details=ScrolledText(self.expander.content,height=8,wrap='word',font=theme.body,background=CANVAS,foreground=INK,relief='flat',padx=theme.u(12),pady=theme.u(12))
        theme.text_surface(self.details,background=CANVAS)
        self.details.pack(fill='both',expand=True);self.details.configure(state='disabled')

    def activate(self):
        if not self.winfo_manager():self.pack(fill='x',pady=self.theme.u(10))

    def show_report(self,report):
        self.activate()
        retained=report.source_metadata.get('quarantined_count',report.source_metadata.get('metadata',{}).get('external_parse',{}).get('quarantined_count',0))
        self.labels[0].set('新增消息')
        for variable,value in zip(self.values,(report.success_count,report.duplicated_count,report.failed_count,retained)):variable.set(str(value))
        states={'success':'操作完成','partial':'部分记录已归档，请检查失败项','failed':'未导入，请检查详细结果'}
        if report.source_metadata.get('mode')=='streaming-partial-commit':
            states.update(partial='支持的文字已处理，未支持原记录保留',failed='导入中断，已提交批次保留，可核对后恢复',cancelled='后续批次已停止，已提交记录保留，可恢复')
        self.state.set(states.get(report.status,report.status))

    def show_preview(self,result):
        self.activate()
        self.labels[0].set('预览消息')
        for variable in self.values:variable.set('—')
        count=result.get('messages',0);self.values[0].set('—' if count is None else str(count))
        self.state.set('预览检查完成，尚未写入归档；是否可导入以详细校验结果为准。')
