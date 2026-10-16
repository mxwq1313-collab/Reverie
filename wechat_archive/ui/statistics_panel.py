"""Lazy local archive dashboard with cached background aggregation and native charts."""
from datetime import date,timedelta
from pathlib import Path
import queue,threading
import tkinter as tk
from tkinter import ttk
from .common_widgets import ScrollPanel
from ..ai.context import archive_token
from ..services.archive_statistics import archive_statistics


class StatisticsPanel:
    def __init__(self,app,page):
        self.app=app;self.root=app.root;self.events=queue.Queue();self.generation=0;self.job=None;self.draw_job=None;self.closed=False;self.busy=False;self.cache=None;self.data=None;self.pending=None
        u=app.theme.u;head=ttk.Frame(page,padding=u(20));head.pack(fill='x');head.columnconfigure(0,weight=1)
        ttk.Label(head,text='聊天足迹',font=app.theme.title).grid(row=0,column=0,sticky='w')
        ttk.Button(head,text='刷新统计',command=lambda:self.refresh(True),style='Quiet.TButton').grid(row=0,column=1)
        self.caption=tk.StringVar(self.root);ttk.Label(head,textvariable=self.caption,style='Hint.TLabel',wraplength=u(660)).grid(row=1,column=0,columnspan=2,sticky='w',pady=(u(6),0))
        row=ttk.Frame(head);row.grid(row=2,column=0,columnspan=2,sticky='w',pady=(u(12),0))
        self.mode=tk.StringVar(self.root,value='当前身份')
        for text in ('当前身份','整个归档'):ttk.Radiobutton(row,text=text,variable=self.mode,value=text,command=self.refresh).pack(side='left',padx=(0,u(16)))
        self.scroll=ScrollPanel(page,app.theme);self.scroll.pack(fill='both',expand=True);self.body=self.scroll.body
        self.state=tk.StringVar(self.root,value='打开归档后，看看聊天留下的足迹。')
        self.notice=ttk.Label(self.body,textvariable=self.state,style='Hint.TLabel',wraplength=u(640));self.notice.pack(anchor='w',pady=u(12))
        self.content=ttk.Frame(self.body);self.content.pack(fill='both',expand=True)
        self.scroll.canvas.bind('<Configure>',lambda _:self.schedule_draw(),add='+')

    def binding(self):
        path=self.app.controller.database
        return (str(path),archive_token(path),self.app.owner_id if self.mode.get()=='当前身份' else None) if path else None

    def refresh(self,force=False):
        if self.closed:return
        try:key=self.binding()
        except Exception as error:self.state.set(str(error));return
        if key is None:self.data=None;self.clear();self.state.set('先导入文件或打开已有归档，再查看统计。');return
        self.caption.set('当前归档 · '+self.mode.get()+' · 北京时间 · 仅分析已归档内容')
        if self.mode.get()=='当前身份' and key[2] is None:self.data=None;self.cache=None;self.clear();self.state.set('请先选择查看身份。');return
        if self.busy:self.pending=(key,force);return
        if key==self.cache and not force:
            self.schedule_draw();return
        self.data=None;self.cache=None;self.clear()
        self.generation+=1;generation=self.generation;self.busy=True;self.state.set('正在整理聊天足迹…')
        def work():
            try:self.events.put((generation,key,archive_statistics(key[0],key[2]),None))
            except Exception as error:self.events.put((generation,key,None,str(error)))
        threading.Thread(target=work,daemon=True,name='sixu-statistics').start()
        if self.job is None:self.job=self.root.after(70,self.poll)

    def poll(self):
        self.job=None
        if self.closed:return
        try:
            while True:
                generation,key,data,error=self.events.get_nowait()
                if generation!=self.generation:continue
                self.busy=False
                if self.pending is not None:
                    pending=self.pending;self.pending=None;self.refresh(pending[1]);continue
                try:valid=key==self.binding()
                except Exception:valid=False
                if not valid:self.data=None;self.cache=None;self.clear();self.state.set('归档或身份已变化，请刷新统计。');continue
                if error:self.state.set('统计未完成：'+error);continue
                self.data=data;self.cache=key;self.state.set('')
                if self.app.current_page=='统计':self.draw()
        except queue.Empty:pass
        if self.busy and self.job is None:self.job=self.root.after(70,self.poll)

    def clear(self):
        self.drawn=None
        for widget in self.content.winfo_children():widget.destroy()

    def schedule_draw(self):
        if self.closed or not self.data:return
        if self.draw_job:self.root.after_cancel(self.draw_job)
        self.draw_job=self.root.after(100,self.draw)

    def draw(self):
        self.draw_job=None
        if self.closed or not self.data or self.app.current_page!='统计':return
        key=(self.cache,self.app.theme.generation,self.scroll.canvas.winfo_width(),self.app.theme.body)
        if key==getattr(self,'drawn',None):return
        self.clear();self.drawn=key;t=self.app.theme;u=t.u;p=t.palette;data=self.data;s=data['summary'];f=data['fun']
        if not s['total']:self.state.set('这个范围还没有已导入消息。');return
        cards=ttk.Frame(self.content);cards.pack(fill='x',pady=(0,u(20)))
        values=[('留下的消息',f"{s['total']:,}"),('相遇的会话',str(s['conversations'])),('活跃的日子',str(s['active_days'])),('写下的文字',f"{s['text_characters']:,}")]
        available=self.scroll.canvas.winfo_width()-u(48);minimum=u(max(160,t.text_size*7+24));cols=4 if available>=minimum*4 else 2 if available>=minimum*2 else 1
        for index,(label,value) in enumerate(values):
            block=ttk.Frame(cards,padding=u(12),style='Canvas.TFrame');block.grid(row=index//cols,column=index%cols,sticky='ew',padx=(0,u(8)),pady=(0,u(8)));cards.columnconfigure(index%cols,weight=1)
            ttk.Label(block,text=value,font=t.section,background=p['CANVAS']).pack(anchor='w');ttk.Label(block,text=label,style='Hint.TLabel',background=p['CANVAS']).pack(anchor='w')
        peak=f['peak_day'];notes=f"最长连续活跃 {f['longest_streak']} 天   ·   夜间消息 {f['night_ratio']:.1%}   ·   平均文字 {f['mean_text_length']:.0f} 字 / 条"
        ttk.Label(self.content,text=notes,wraplength=max(u(240),self.scroll.canvas.winfo_width()-u(60)),style='Hint.TLabel').pack(anchor='w',pady=(0,u(12)))
        if peak:ttk.Label(self.content,text=f"最热闹的一天：{peak['day']}，留下 {peak['count']:,} 条消息",style='Hint.TLabel').pack(anchor='w',pady=(0,u(16)))
        if not data['daily']:
            self.state.set('消息日期无法解析；保留数量统计。');return
        self.heading('聊天日历 · 最新消息所在的 13 周')
        heat=tk.Canvas(self.content,height=u(132),background=p['PAPER'],highlightthickness=0);heat.pack(fill='x',pady=(u(8),u(20)))
        latest=date.fromisoformat(data['daily'][-1]['day']);start=latest-timedelta(days=latest.weekday(),weeks=12);counts={x['day']:x['count'] for x in data['daily']};maximum=max(counts.get((start+timedelta(days=i)).isoformat(),0) for i in range(91)) or 1
        for index in range(91):
            day=start+timedelta(days=index);value=counts.get(day.isoformat(),0);col=index//7;row=index%7;x=u(38+col*19);y=u(5+row*17)
            color=p['ACCENT'] if value>maximum*.6 else p['SELECTED'] if value else p['HOVER']
            shape=heat.create_rectangle(x,y,x+u(13),y+u(12),fill=color,outline='');heat.tag_bind(shape,'<Enter>',lambda _,d=day,v=value:self.state.set(f'{d.isoformat()} · {v:,} 条消息'));heat.tag_bind(shape,'<Leave>',lambda _:self.state.set(''))
        for row,text in ((0,'一'),(2,'三'),(4,'五'),(6,'日')):heat.create_text(u(12),u(11+row*17),text=text,fill=p['SECONDARY'],font=t.small)
        self.heading('一天中的聊天节奏');self.bars(data['hours'],[f'{x:02d}' if x%4==0 else '' for x in range(24)],170)
        self.heading('一周里的聊天节奏');self.bars(data['weekdays'],list('一二三四五六日'),145)
        self.heading('话题里的声音')
        for row in data['talkers']:
            line=ttk.Frame(self.content);line.pack(fill='x',pady=u(4));name=ttk.Label(line,text=row['name'][:30]);name._raw_text=True;name.pack(side='left');ttk.Label(line,text=f"{row['count']:,} 条 · {row['count']/s['total']:.1%}",style='Hint.TLabel').pack(side='right')
        self.heading('内容与收藏')
        names={'text':'文字','image':'图片 / 表情','audio':'语音','video':'视频','file':'文件','location':'位置','system':'系统 / 分享'}
        ttk.Label(self.content,text='   ·   '.join(names.get(k,k)+' '+str(v) for k,v in data['kinds'].items()),wraplength=u(600),style='Hint.TLabel').pack(anchor='w',pady=u(8))
        m=data['media'];ttk.Label(self.content,text=f"去重附件 {m['resources']:,} 个 · 可用 {m['available']:,} 个 · 未取得 {m['missing']:,} 个 · 已保存 {m['bytes']/1024/1024:.1f} MiB",wraplength=u(600),style='Hint.TLabel').pack(anchor='w',pady=(0,u(12)))
        ttk.Label(self.content,text='夜间为 22:00–05:59；图片与表情按归档类型合并计数。统计覆盖当前归档内容，不能代表尚未导入的历史。',wraplength=u(600),style='Hint.TLabel').pack(anchor='w',pady=u(12))
        t.apply_tree(self.content);self.app.localizer.apply(self.content,());t.wheel_router.attach(self.content)

    def heading(self,text):ttk.Label(self.content,text=text,font=self.app.theme.name).pack(anchor='w',pady=(self.app.theme.u(16),0))

    def bars(self,values,labels,height):
        t=self.app.theme;u=t.u;p=t.palette;width=max(u(260),self.scroll.canvas.winfo_width()-u(52));chart=tk.Canvas(self.content,width=width,height=u(height),background=p['PAPER'],highlightthickness=0);chart.pack(fill='x',pady=u(12))
        maximum=max(values) or 1;step=(width-u(12))/len(values);bottom=u(height-28)
        for index,value in enumerate(values):
            x=u(6)+step*index;top=bottom-(height-55)*t.scale*value/maximum
            item=chart.create_rectangle(x,top,x+max(2,step-u(5)),bottom,fill=p['ACCENT'] if value==maximum else p['SELECTED'],outline='');chart.tag_bind(item,'<Enter>',lambda _,i=index,v=value:self.state.set(f'{labels[i] or i} · {v:,} 条消息'));chart.tag_bind(item,'<Leave>',lambda _:self.state.set(''))
            chart.create_text(x+step/2,bottom+u(15),text=labels[index],font=t.small,fill=p['SECONDARY'])

    def close(self):
        self.closed=True;self.generation+=1
        for job in (self.job,self.draw_job):
            if job:self.root.after_cancel(job)
