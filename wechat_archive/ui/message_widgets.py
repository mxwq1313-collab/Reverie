"""真实联系人卡片与可选中原文的气泡时间线。"""
from datetime import datetime,timedelta,timezone
import tkinter as tk
import time
from tkinter import ttk
from .theme import PAPER,CANVAS,SIDEBAR,INK,SECONDARY,SELECTED,OWN,ACCENT,LINE,HOVER
from .rounded import RoundedSurface
from .slim_scrollbar import SlimScrollbar

ZONE=timezone(timedelta(hours=8))


def date_heading(stamp,language='zh_CN'):
    if language=='en_US':return f'{stamp.year:04d}-{stamp.month:02d}-{stamp.day:02d}'
    return f'{stamp.year:04d}年{stamp.month:02d}月{stamp.day:02d}日'


def display_time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZONE)


class ContactList(ttk.Frame):
    def __init__(self,parent,theme,on_select):
        super().__init__(parent);self.theme=theme;self.on_select=on_select;self.rows=[];self.selected=None;self.cards={};self.summaries={};self.label_key=None
        self.canvas=tk.Canvas(self,background=PAPER,takefocus=1,highlightthickness=0)
        bar=SlimScrollbar(self,theme,command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set);self.canvas.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
        self.body=tk.Frame(self.canvas,background=PAPER)
        self.window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize)
        theme.wheel_router.register(self,self.canvas,canvas=True)
        self.canvas.bind('<Up>',lambda _:self.move_selected(-1))
        self.canvas.bind('<Down>',lambda _:self.move_selected(1))
        self.canvas.bind('<Home>',lambda _:self.move_selected(-len(self.rows)))
        self.canvas.bind('<End>',lambda _:self.move_selected(len(self.rows)))
        self.canvas.bind('<Return>',lambda _:self.activate_selected())

    def wheel(self,event):return self.theme.wheel_router.wheel(event)
    def resize(self,event):
        self.canvas.itemconfigure(self.window,width=event.width)
        key=(event.width,self.theme.generation,self.theme.body)
        if key==self.label_key:return
        self.label_key=key
        for row in self.rows:self.update_labels(row,event.width)

    def set_rows(self,rows,selected=None,append=False):
        chosen=str(selected) if selected is not None else None
        if not append and list(rows)==self.rows:
            previous=self.selected;self.selected=chosen
            if previous!=chosen:
                if previous in self.cards:self.paint(previous,False)
                if chosen in self.cards:self.paint(chosen,False)
            return
        if not append:
            for widget in self.body.winfo_children():widget.destroy()
            self.rows=[];self.cards={};self.summaries={}
        self.rows.extend(rows);self.label_key=None;self.selected=chosen
        self.body.configure(background=self.theme.palette['PAPER']);self.canvas.configure(background=self.theme.palette['PAPER'])
        u=self.theme.u
        fresh=[]
        for row in rows:
            key=str(row['id']);card=RoundedSurface(self.body,self.theme,PAPER,PAPER,radius=2,padding=9)
            fresh.append(card)
            card.configure(cursor='hand2');card.pack(fill='x',padx=u(3),pady=u(3));content=card.content;content.columnconfigure(1,weight=1)
            avatar=tk.Canvas(content,background=PAPER,width=u(34),height=u(34),highlightthickness=0)
            # A softly rounded square matches the WeChat avatar frame.
            self.draw_avatar(avatar,row)
            avatar.grid(row=0,column=0,rowspan=3,sticky='n',padx=(0,u(9)))
            name=tk.Label(content,anchor='w',background=PAPER,foreground=INK,font=self.theme.name)
            name._raw_text=True
            name.grid(row=0,column=1,sticky='ew')
            stamp=display_time(row['last_time']).strftime('%m-%d') if row.get('last_time') else ''
            time=tk.Label(content,text=stamp,background=PAPER,foreground=SECONDARY,font=self.theme.small)
            time.grid(row=0,column=2,sticky='e')
            preview=tk.Label(content,anchor='w',background=PAPER,foreground=SECONDARY,font=self.theme.small)
            preview._raw_text=True
            # Kept as an empty compatibility handle; recent message text is never shown.
            count=tk.Label(content,text=f"{row['message_count']} 条已归档",anchor='w',background=PAPER,foreground=SECONDARY,font=self.theme.small)
            count.grid(row=1,column=1,columnspan=2,sticky='ew',pady=(u(3),0))
            self.cards[key]=(card,name,preview,time,count)
            for widget in (card,content,*content.winfo_children()):
                widget.bind('<Button-1>',lambda e,value=key:self.choose(value))
                widget.bind('<Enter>',lambda e,value=key:self.paint(value,True))
                widget.bind('<Leave>',lambda e,value=key:self.paint(value,False))
            if 'own_count' in row:
                count.configure(text=f"{row['message_count']:,} 条 · 本人 {row.get('own_ratio',0):.0%}")
                count.configure(wraplength=u(190))
            if row.get('kind')=='group':
                details=tk.Frame(self.body,background=PAPER)
                fresh.append(details)
                def toggle(button,section=details,card=card,total=len(row.get('members',[]))):
                    expanded=not bool(section.winfo_manager())
                    if not expanded:section.pack_forget()
                    else:section.pack(fill='x',after=card,padx=u(12),pady=(0,u(8)))
                    button.configure(text=f"{'▾' if expanded else '▸'} 成员 {total}")
                opener=tk.Button(content,text=f"▸ 成员 {len(row.get('members',[]))}",font=self.theme.small,background=PAPER,foreground=SECONDARY,relief='flat',borderwidth=0,highlightthickness=0,cursor='hand2')
                opener.configure(command=lambda button=opener,action=toggle:action(button))
                opener.grid(row=2,column=1,columnspan=2,sticky='w')
                for member in row.get('members',[]):
                    label=tk.Label(details,text=f"{member['nickname']} · {member['message_count']} 条 · {member['ratio']:.1%}",font=self.theme.small,background=PAPER,foreground=SECONDARY,anchor='w',wraplength=u(200))
                    label._raw_text=True;label.pack(fill='x',pady=u(3))
            self.update_labels(row,max(self.canvas.winfo_width(),u(260)))
            self.paint(key,False)
        for widget in fresh:
            self.theme.wheel_router.attach(widget)
            if self.theme.active_mode!='light' and not isinstance(widget,RoundedSurface):self.theme.apply_tree(widget)

    def set_rows_incremental(self,rows,selected=None):
        rows=list(rows)
        if rows==self.rows:return self.set_rows(rows,selected)
        if getattr(self,'render_job',None):self.after_cancel(self.render_job)
        self.render_token=getattr(self,'render_token',0)+1;token=self.render_token
        retired=getattr(self,'retired_widgets',{})
        for widget in self.body.winfo_children():widget.pack_forget();retired[str(widget)]=widget
        self.retired_widgets=retired
        if not getattr(self,'cleanup_job',None):self.cleanup_job=self.after(1,self.retire_batch)
        self.rows=[];self.cards={};self.summaries={};self.label_key=None;self.selected=str(selected) if selected is not None else None
        index=0;self.rendering=True
        def batch():
            nonlocal index
            self.render_job=None
            if token!=self.render_token:return
            chunk=rows[index:index+5];index+=len(chunk);self.set_rows(chunk,self.selected,append=True)
            if index<len(rows):self.render_job=self.after(1,batch)
            else:self.rendering=False
        self.render_job=self.after(1,batch)
    def retire_batch(self):
        self.cleanup_job=None
        for key in list(self.retired_widgets)[:5]:
            widget=self.retired_widgets.pop(key)
            if widget.winfo_exists():widget.destroy()
        if self.retired_widgets:self.cleanup_job=self.after(1,self.retire_batch)

    def destroy(self):
        for name in ('render_job','cleanup_job'):
            if getattr(self,name,None):self.after_cancel(getattr(self,name))
        super().destroy()

    def update_labels(self,row,width):
        card,name,preview,_,count=self.cards[str(row['id'])]
        count.configure(wraplength=max(self.theme.u(70),width-self.theme.u(78)))
        name.configure(text=self.theme.elide(row['nickname'],max(self.theme.u(40),width-self.theme.u(113))))
        preview.configure(text='')

    def draw_avatar(self,canvas,row):
        u=self.theme.u
        path=row.get('avatar')
        if path:
            try:
                from pathlib import Path
                from PIL import Image,ImageTk,ImageOps,ImageDraw,ImageChops
                source=Path(path)
                if source.is_file() and source.stat().st_size<=4*1024*1024:
                    with Image.open(source) as image:
                        if image.width*image.height>4_000_000:raise ValueError('image budget')
                        image=ImageOps.fit(image.convert('RGBA'),(u(34),u(34)),method=Image.Resampling.LANCZOS)
                    mask=Image.new('L',image.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,image.width-1,image.height-1),radius=u(6),fill=255);image.putalpha(ImageChops.multiply(mask,image.getchannel('A')))
                    canvas.avatar_image=ImageTk.PhotoImage(image,master=canvas)
                    canvas.create_image(u(17),u(17),image=canvas.avatar_image);canvas.avatar_available=True;return
            except (OSError,ValueError,tk.TclError):pass
        from .rounded import rounded_points
        points=[value+u(1) for value in rounded_points(u(32),u(32),u(6))]
        canvas.create_polygon(points,fill=SIDEBAR,outline=SIDEBAR)
        # Neutral person silhouette is used only when WeChat has no verified cache.
        canvas.create_oval(u(12),u(7),u(22),u(17),fill=SECONDARY,outline='')
        canvas.create_arc(u(7),u(18),u(27),u(37),start=0,extent=180,fill=SECONDARY,outline='')
        canvas.avatar_available=False

    def paint(self,key,hover):
        if key not in self.cards:return
        background=SELECTED if key==self.selected else HOVER if hover else PAPER
        card,*_=self.cards[key];card.paint(background)
        for widget in card.content.winfo_children():widget.configure(background=background)
        if self.theme.active_mode!='light':self.theme.apply_tree(card)

    def choose(self,key):
        self.canvas.focus_set();self.selection_set(key);self.on_select()

    def move_selected(self,step):
        keys=list(self.cards)
        if not keys:return 'break'
        index=keys.index(self.selected) if self.selected in keys else (-1 if step>0 else 0)
        self.selection_set(keys[max(0,min(len(keys)-1,index+step))])
        self.update_idletasks();card=self.cards[self.selected][0]
        top=card.winfo_y();bottom=top+card.winfo_height();visible=self.canvas.canvasy(0)
        region=self.canvas.bbox('all')
        if region:
            if top<visible:self.canvas.yview_moveto(top/max(1,region[3]))
            elif bottom>visible+self.canvas.winfo_height():self.canvas.yview_moveto((bottom-self.canvas.winfo_height())/max(1,region[3]))
        return 'break'

    def activate_selected(self):
        if self.selected in self.cards:self.choose(self.selected)
        return 'break'
    def selection_set(self,key):
        previous=self.selected;self.selected=str(key)
        if previous==self.selected:return
        if previous in self.cards:self.paint(previous,False)
        if self.selected in self.cards:self.paint(self.selected,False)
    def selection(self):return (self.selected,) if self.selected in self.cards else ()
    def get_children(self):return tuple(self.cards)


class BubbleTimeline(ttk.Frame):
    def __init__(self,parent,theme):
        super().__init__(parent);self.theme=theme;self.rows=[];self.bubbles={};self.last_date=None;self.last_width=0;self.layout_job=None
        self.canvas=tk.Canvas(self,background=CANVAS,highlightthickness=0)
        bar=SlimScrollbar(self,theme,command=self.canvas.yview);self.scrollbar=bar;self.canvas.configure(yscrollcommand=self.scrolled)
        self.canvas.pack(side='left',fill='both',expand=True);bar.pack(side='right',fill='y')
        self.body=tk.Frame(self.canvas,background=CANVAS)
        self.window=self.canvas.create_window(0,0,window=self.body,anchor='nw')
        self.body.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',self.resize);theme.wheel_router.register(self,self.canvas,canvas=True)
        self.canvas.bind('<Map>',lambda _:self.queue_reflow())
        self.empty=None;self.thumbnails=[]

    def wheel(self,event):return self.theme.wheel_router.wheel(event)
    def clear(self,defer=False):
        self.render_after=None;self.pending_anchor=None
        if hasattr(self,'measure_cache'):self.measure_cache.clear()
        if getattr(self,'render_after_job',None):self.after_cancel(self.render_after_job);self.render_after_job=None
        self.completed_layout=None
        self.render_token=getattr(self,'render_token',0)+1;self.rendering=False
        if getattr(self,'render_job',None):self.after_cancel(self.render_job);self.render_job=None
        if getattr(self,'media_layout_job',None):self.after_cancel(self.media_layout_job);self.media_layout_job=None
        if getattr(self,'restore_job',None):self.after_cancel(self.restore_job);self.restore_job=None
        if getattr(self,'finish_job',None):self.after_cancel(self.finish_job);self.finish_job=None
        self.reflow_busy=False
        if getattr(self,'layout_step_job',None):self.after_cancel(self.layout_step_job);self.layout_step_job=None
        for _,canvas in self.thumbnails:
            if canvas.winfo_exists():canvas._thumbnail_visible=False
        widgets=self.body.winfo_children()
        if defer:
            retired=getattr(self,'retired_widgets',{})
            for widget in widgets:widget.pack_forget();retired[str(widget)]=widget
            self.retired_widgets=retired
            if not getattr(self,'cleanup_job',None):self.cleanup_job=self.after(1,self.retire_batch)
        else:
            for widget in widgets:widget.destroy()
        self.rows=[];self.bubbles={};self.thumbnails=[];self.last_date=None;self.empty=None;self.layout_revision=getattr(self,'layout_revision',0)+1
        self.canvas.configure(scrollregion=(0,0,0,0));self.canvas.yview_moveto(0)

    def retire_batch(self):
        self.cleanup_job=None
        for key in list(self.retired_widgets)[:6]:
            widget=self.retired_widgets.pop(key)
            if widget.winfo_exists():widget.destroy()
        if self.retired_widgets:self.cleanup_job=self.after(1,self.retire_batch)

    def set_rows_incremental(self,rows,owner,keyword='',all_chats=False,context=None,append=False):
        rows=list(rows);signature=(owner,keyword,all_chats)
        if not append and self.rows==rows and getattr(self,'render_signature',None)==signature and self.bubbles:return
        if append and getattr(self,'rendering',False) and self.render_signature==signature:
            self.render_rows.extend(rows);return
        if not append:self.clear(defer=True)
        elif getattr(self,'render_job',None):self.after_cancel(self.render_job)
        self.render_signature=signature;self.rendering=True;self.render_rows=rows;self.render_index=0
        self.render_token=getattr(self,'render_token',0)+1;token=self.render_token
        def batch():
            self.render_job=None
            if token!=self.render_token:return
            chunk=self.render_rows[self.render_index:self.render_index+5];self.render_index+=len(chunk)
            self.set_rows(chunk,owner,keyword,all_chats,context,append=True)
            if self.render_index<len(self.render_rows):self.render_job=self.after(12,batch)
            else:
                self.rendering=False
                callback=getattr(self,'render_after',None);self.render_after=None
                if callback:self.after_render(callback)
                app=getattr(self,'app',None)
                if app:
                    app.update_message_count(app.loaded_offset+len(app.message_rows)<app.message_total)
                    if app.status.get().startswith('正在显示'):app.status.set('已加载聊天记录。')
        self.render_job=self.after(1,batch)

    def after_render(self,callback):
        if getattr(self,'rendering',False):self.render_after=callback;return
        if getattr(self,'render_after_job',None):self.after_cancel(self.render_after_job)
        def run():
            self.render_after_job=None
            if getattr(self,'reflow_busy',False) or self.layout_job or getattr(self,'rendering',False):
                self.render_after_job=self.after(10,run);return
            self.update_idletasks();callback()
        self.render_after_job=self.after_idle(run)

    def show_state(self,title,hint,actions=()):
        self.clear();self.empty=tk.Frame(self.body,background=CANVAS,pady=self.theme.u(65))
        self.empty.pack(fill='x',expand=True,padx=self.theme.u(25))
        tk.Label(self.empty,text=title,background=CANVAS,foreground=INK,font=self.theme.title).pack(pady=self.theme.u(10))
        self.state_hint=tk.Label(self.empty,text=hint,background=CANVAS,foreground=SECONDARY,font=self.theme.body,wraplength=self.theme.u(470))
        self.state_hint.pack(pady=self.theme.u(8))
        row=tk.Frame(self.empty,background=CANVAS);row.pack(pady=self.theme.u(12))
        for label,command in actions:ttk.Button(row,text=label,command=command).pack(side='left',padx=self.theme.u(5))
        self.theme.wheel_router.attach(self.body)

    def set_rows(self,rows,owner,keyword='',all_chats=False,context=None,append=False):
        self.thumbnail_budget=8
        rows=list(rows);signature=(owner,keyword,all_chats)
        if not append and self.rows==rows and getattr(self,'render_signature',None)==signature and self.bubbles:
            self.canvas.yview_moveto(0);return
        self.render_signature=signature
        self.layout_revision=getattr(self,'layout_revision',0)+1
        top=max(0,self.canvas.canvasy(0)) if append else 0
        if not append:self.clear()
        self.rows.extend(rows)
        u=self.theme.u
        fresh=[]
        for row in rows:
            stamp=display_time(row['create_time']);date=date_heading(stamp)
            if date!=self.last_date:
                date_label=tk.Label(self.body,text=date_heading(stamp,self.theme.language),background=self.theme.palette['CANVAS'],foreground=self.theme.palette['SECONDARY'],font=self.theme.small,pady=u(12))
                date_label._date_value=stamp;date_label.pack(fill='x')
                fresh.append(date_label)
                self.last_date=date
            own=row['sender_id']==owner
            container=tk.Frame(self.body,background=CANVAS,padx=u(16));container.pack(fill='x',pady=(0,u(16)))
            fresh.append(container)
            meta=tk.Frame(container,background=CANVAS);meta.pack(anchor='e' if own else 'w')
            caption=f"{row['sender_name']} · {stamp.strftime('%H:%M:%S')}"
            if all_chats:
                peer=(row.get('chat_title') or '群聊') if row.get('chat_kind')=='group' else row['receiver_name'] if own else row['sender_name'];caption+=' · 会话：'+peer
            label=tk.Label(meta,text=caption,background=CANVAS,foreground=SECONDARY,font=self.theme.small,anchor='e' if own else 'w')
            label.pack(side='left')
            if all_chats and context:
                ttk.Button(meta,text='查看上下文',command=lambda value=row['id']:context(value)).pack(side='left',padx=u(7))
            color=OWN if own else PAPER
            bubble=tk.Canvas(container,background=CANVAS,highlightthickness=0,bd=0)
            bubble.pack(anchor='e' if own else 'w',pady=(u(5),0))
            text=tk.Text(bubble,wrap='word',font=self.theme.body,background=CANVAS,foreground=INK,relief='flat',bd=0,highlightthickness=0,
                         padx=0,pady=0,undo=False,exportselection=True,spacing1=u(1),spacing3=u(3),cursor='xterm')
            from .media_widgets import present_content
            display_text=present_content(row)
            from ..message_content import forwarded_document
            forward=forwarded_document(row.get('content')) if row.get('msg_type')=='system' else None
            if forward and forward['items']:display_text=f"聊天记录 · {forward['total']} 条"
            media_only=bool(row.get('attachments')) and (row.get('msg_type') in ('image','emoji','audio','video','file') or display_text.startswith(('[图片','[表情','[文件]','[语音]','[视频]')))
            if forward and forward['items']:media_only=True
            if media_only:display_text=''
            text.insert('1.0',display_text)
            from .inline_emojis import render_inline
            render_inline(text,self.theme)
            text.configure(state='disabled')
            if media_only:bubble.pack_forget()
            text.tag_configure('match',background='#ffe39a',foreground=INK)
            if keyword:
                start='1.0'
                while True:
                    index=text.search(keyword,start,stopindex='end',exact=True,elide=True)
                    if not index:break
                    end=f'{index}+{len(keyword)}c';text.tag_add('match',index,end);start=end
            menu=tk.Menu(text,tearoff=False)
            menu.add_command(label='复制选中文字',command=lambda widget=text:self.copy_selection(widget))
            menu.add_command(label='复制这条原文',command=lambda value=row['content']:self.copy_raw(value))
            text.bind('<Button-3>',lambda event,value=menu:value.tk_popup(event.x_root,event.y_root))
            text.bind('<Control-c>',lambda event,widget=text:self.copy_selection(widget))
            text.bind('<Control-a>',lambda event,widget=text:self.select_all(widget))
            self.bubbles[row['id']]={'row':row,'display_text':display_text,'outer':container,'bubble':bubble,'text':text,'color':color,'label':label,'media_only':media_only}
            from .media_widgets import attachment_widgets
            attachment_widgets(self,container,row)
        for widget in fresh:self.theme.wheel_router.attach(widget)
        self.pending_top=top;self.queue_reflow(immediate=True)

    def selectable_texts(self):
        for value in self.bubbles.values():
            yield value['text']
            forward=value.get('forward')
            if forward:
                for _,_,text in forward.rendered:
                    if text is not None:yield text

    def select_all(self,widget):widget.tag_add('sel','1.0','end-1c');return 'break'
    def copy_selection(self,widget):
        if widget.tag_ranges('sel'):self.copy_raw(widget.get('sel.first','sel.last'))
        return 'break'
    def copy_raw(self,value):self.clipboard_clear();self.clipboard_append(value or '')
    def get(self,start='1.0',end='end'):return '\n\n'.join(row['content'] or '' for row in self.rows)

    def resize(self,event):
        if abs(event.width-self.last_width)<3:return
        if getattr(self,'completed_layout',None):self.resizing_until=max(getattr(self,'resizing_until',0),time.monotonic()+.14)
        self.remember_scroll_anchor()
        self.last_width=event.width
        self.queue_reflow()

    def queue_reflow(self,immediate=False):
        key=(self.canvas.winfo_width(),self.theme.generation,getattr(self,'layout_revision',0))
        if key==getattr(self,'completed_layout',None) and not getattr(self,'reflow_busy',False):
            self.refresh_visible();return
        if self.layout_job:self.after_cancel(self.layout_job)
        self.layout_job=self.after(120,self.reflow) if self.bubbles and getattr(self,'completed_layout',None) and not getattr(self,'rendering',False) and not immediate else self.after_idle(self.reflow)

    def reflow(self):
        remaining=getattr(self,'resizing_until',0)-time.monotonic()
        if remaining>0 and getattr(self,'completed_layout',None):
            self.layout_job=self.after(max(1,int(remaining*1000)+1),self.reflow);return
        if getattr(self,'reflow_busy',False):
            self.layout_job=None;self.reflow_again=True;return
        if self.layout_job:
            try:self.after_cancel(self.layout_job)
            except tk.TclError:pass
        self.layout_job=None
        self.reflow_busy=True;self.reflow_again=False
        start_width=self.canvas.winfo_width()
        if start_width<3:
            self.reflow_busy=False;self.layout_job=self.after(20,self.reflow);return
        if getattr(self,'body_width',None)!=start_width:
            self.canvas.itemconfigure(self.window,width=start_width);self.body_width=start_width
        u=self.theme.u;width=max(u(220),start_width-u(32));limit=min(u(720),int(width*.85));prepared=[]
        line_height=self.theme.font.metrics('linespace')+u(4)
        values=iter(tuple(self.bubbles.values()))
        token=getattr(self,'render_token',0)
        generation=self.theme.generation
        revision=getattr(self,'layout_revision',0)
        def prepare_batch():
            self.layout_step_job=None
            if token!=getattr(self,'render_token',0):return
            started=time.perf_counter()
            for value in values:
                text=value['text'];bubble=value['bubble']
                if value.get('media_only'):
                    value['label'].configure(wraplength=width)
                    if value.get('theme_generation')!=generation:self.theme.apply_tree(value['outer']);value['theme_generation']=generation
                else:
                    if value.get('font_generation')!=self.theme.body:
                        from .inline_emojis import resize_inline,natural_width
                        resize_inline(text,self.theme)
                        value['natural']=natural_width(value['display_text'],self.theme)
                        value['font_generation']=self.theme.body
                    bubble_width=max(u(80),min(limit,value['natural']+u(40)))
                    layout_key=(bubble_width,self.theme.body,self.theme.active_mode)
                    if value.get('layout_key')!=layout_key:
                        value['layout_key']=layout_key
                        if value.get('collapsed_children'):
                            self.estimate_collapsed(value,bubble_width,line_height)
                        else:
                            text.place(x=u(14),y=u(10),width=bubble_width-u(28),height=value.get('text_height',line_height))
                            value['visible']=None
                            bubble.configure(width=bubble_width)
                            value['label'].configure(wraplength=width)
                            prepared.append((value,bubble_width))
                if getattr(getattr(self,'app',None),'background_browsing',True) and time.perf_counter()-started>.006:
                    self.layout_step_job=self.after(1,prepare_batch);return
            self.finish_job=self.after_idle(lambda:self.finish_reflow(prepared,start_width,width,line_height,revision,generation))
        prepare_batch()

    def finish_reflow(self,prepared,start_width,width,line_height,revision=None,generation=None):
        self.finish_job=None;u=self.theme.u
        revision=getattr(self,'layout_revision',0) if revision is None else revision
        generation=self.theme.generation if generation is None else generation
        token=getattr(self,'render_token',0);values=iter(prepared)
        def finish_batch():
            self.finish_job=None
            if token!=getattr(self,'render_token',0):return
            started=time.perf_counter()
            for value,bubble_width in values:
                if not value['text'].winfo_exists():continue
                text=value['text'];bubble=value['bubble']
                count=text.count('1.0','end-1c','update','displaylines');lines=(count[0] if isinstance(count,tuple) else count or 0)+1
                self.remember_measure(value,bubble_width,line_height,lines)
                height=lines*line_height+u(20);value['height']=height
                value['layout_measured']=True
                value['text_width']=bubble_width-u(28);value['text_height']=height-u(20);bubble.configure(height=height)
                if value.get('collapsed_children'):self.size_collapsed_row(value)
                if value['color']==OWN:
                    if bubble.find_withtag('shape'):bubble.coords('shape',bubble_width-2,u(10),bubble_width-2,height-u(10));bubble.itemconfigure('shape',fill=self.theme.palette['ACCENT'])
                    else:bubble.create_line(bubble_width-2,u(10),bubble_width-2,height-u(10),fill=self.theme.palette['ACCENT'],width=u(2),tags='shape')
                bubble.tag_lower('shape')
                if self.theme.active_mode!='light' and value.get('theme_generation')!=generation:
                    self.theme.apply_tree(value['outer']);value['theme_generation']=generation
                if getattr(getattr(self,'app',None),'background_browsing',True) and time.perf_counter()-started>.006:
                    self.finish_job=self.after(1,finish_batch);return
            if self.empty:self.state_hint.configure(wraplength=max(u(160),width-u(40)))
            if getattr(self,'restore_job',None):self.after_cancel(self.restore_job)
            self.restore_job=self.after_idle(self.restore_scroll)
            self.reflow_busy=False
            if not self.reflow_again and revision==getattr(self,'layout_revision',0) and generation==self.theme.generation:
                self.completed_layout=(start_width,generation,revision)
            else:self.reflow_again=True
            if self.reflow_again or self.canvas.winfo_width()!=start_width:self.queue_reflow()
        finish_batch()

    def scrolled(self,first,last):
        self.scrollbar.set(first,last)
        if not getattr(self,'visibility_job',None):self.visibility_job=self.after_idle(self.refresh_visible)

    def refresh_visible(self):
        job=getattr(self,'visibility_job',None)
        if job:self.after_cancel(job)
        self.visibility_job=None
        remaining=getattr(self,'resizing_until',0)-time.monotonic()
        if remaining>0:
            self.visibility_job=self.after(max(1,int(remaining*1000)+1),self.refresh_visible);return
        top=self.canvas.canvasy(0)-self.theme.u(80);bottom=top+self.canvas.winfo_height()+self.theme.u(160)
        self.thumbnails=[(outer,canvas) for outer,canvas in self.thumbnails if canvas.winfo_exists()]
        for outer,canvas in self.thumbnails:
            if not canvas.winfo_exists():continue
            visible=self.winfo_ismapped() and canvas.winfo_ismapped() and outer.winfo_height()>1 and canvas.winfo_rooty()+canvas.winfo_height()>self.canvas.winfo_rooty()-self.theme.u(80) and canvas.winfo_rooty()<self.canvas.winfo_rooty()+self.canvas.winfo_height()+self.theme.u(80)
            canvas._thumbnail_visible=visible
            if visible and not canvas._thumbnail_requested:
                canvas._thumbnail_requested=True
                self.app.thumbnail_service.submit(canvas._thumbnail_request[0],canvas,*canvas._thumbnail_request[1:])
        for value in self.bubbles.values():
            forward=value.get('forward')
            if forward:forward.update_visible()
            if forward and forward.needs_fit and self.canvas.winfo_ismapped() and self.app.current_page=='聊天归档':
                forward.needs_fit=False;forward.schedule_fit()
            if value['outer'].winfo_height()<=1:continue
            visible=value['outer'].winfo_y()<bottom and value['outer'].winfo_y()+value['outer'].winfo_height()>top
            if getattr(getattr(self,'app',None),'background_browsing',False):
                if visible:self.expand_row(value)
                else:self.collapse_row(value)
            if 'text_height' not in value:continue
            if value.get('visible')==visible:continue
            value['visible']=visible;text=value['text']
            if visible:text.place(x=self.theme.u(14),y=self.theme.u(10),width=value['text_width'],height=value['text_height'])
            elif text.winfo_manager():text.place_forget()

    def size_collapsed_row(self,value):
        height=0
        children=value.get('collapsed_children')
        if not children:return
        for child,options in children:
            padding=options.get('pady',0)
            parts=padding if isinstance(padding,(tuple,list)) else (padding,) if isinstance(padding,(int,float)) else self.tk.splitlist(padding)
            pad=sum(int(x) for x in parts) if len(parts)>1 else int(parts[0])*2 if parts else 0
            height+=child.winfo_reqheight()+pad
        value['outer'].configure(height=max(1,height))

    def remember_scroll_anchor(self):
        if getattr(self,'pending_anchor',None) or not self.bubbles:return
        top=max(0,self.canvas.canvasy(0))
        for message_id,value in self.bubbles.items():
            outer=value['outer']
            if value.get('layout_measured') and outer.winfo_height()>1 and outer.winfo_y()+outer.winfo_height()>=top:
                self.pending_anchor=(message_id,top-outer.winfo_y());return

    def estimate_collapsed(self,value,width,line_height):
        """Reserve offscreen space; exact wrapping is realized when a row is visible."""
        from collections import OrderedDict
        import math
        cache=getattr(self,'measure_cache',None)
        if cache is None:self.measure_cache=cache=OrderedDict()
        u=self.theme.u;available=width-u(28);body=value['display_text'];key=(body,width,self.theme.body,line_height)
        if key in cache:lines=cache[key];estimated=False;cache.move_to_end(key)
        elif value.get('natural',available+1)<=available:lines=len(body.split('\n'));estimated=False
        else:
            old_line=max(1,value.get('measured_line_height',line_height))
            old_lines=max(1,value.get('measured_text_height',value.get('text_height',line_height))/old_line)
            old_width=max(1,value.get('measured_text_width',value.get('text_width',available)))
            old_pixels=max(1,value.get('measured_font_pixels',abs(self.theme.body[1])))
            ratio=abs(self.theme.body[1])/old_pixels
            lines=max(len(body.split('\n')),math.ceil(old_lines*old_width/available*ratio));estimated=True
        height=lines*line_height+u(20)
        value.update(height=height,text_width=available,text_height=height-u(20),estimated_layout=estimated,layout_measured=True)
        value['bubble'].configure(width=width,height=height)
        if value['color']==OWN and value['bubble'].find_withtag('shape'):
            value['bubble'].coords('shape',width-2,u(10),width-2,height-u(10))
        self.size_collapsed_row(value)

    def remember_measure(self,value,bubble_width,line_height,lines):
        from collections import OrderedDict
        value.update(estimated_layout=False,measured_line_height=line_height,measured_font_pixels=abs(self.theme.body[1]),measured_text_height=lines*line_height,measured_text_width=bubble_width-self.theme.u(28))
        if len(value['display_text'])>6000:return
        cache=getattr(self,'measure_cache',None)
        if cache is None:self.measure_cache=cache=OrderedDict()
        key=(value['display_text'],bubble_width,self.theme.body,line_height);cache[key]=lines;cache.move_to_end(key)
        while len(cache)>80:cache.popitem(last=False)

    def measure_collapsed(self,value,width,line_height):
        from collections import OrderedDict
        u=self.theme.u;body=value['display_text'];available=width-u(28)
        cache=getattr(self,'measure_cache',None)
        if cache is None:self.measure_cache=cache=OrderedDict()
        key=(body,width,self.theme.body,line_height)
        if key in cache:
            lines=cache[key];cache.move_to_end(key)
        elif value.get('natural',available+1)<=available:
            lines=len(body.split('\n'))
        else:
            measure=getattr(self,'measure_widget',None)
            if measure is None:
                measure=tk.Text(self.canvas,wrap='word',borderwidth=0,highlightthickness=0,padx=0,pady=0,takefocus=0,exportselection=False)
                self.measure_widget=measure
            measure.configure(font=self.theme.body,spacing1=u(1),spacing3=u(3));measure.place(x=-30000,y=0,width=available,height=line_height)
            if measure.winfo_width()!=available:measure.update_idletasks()
            measure.delete('1.0','end');measure.insert('1.0',body)
            from .inline_emojis import render_inline
            render_inline(measure,self.theme)
            count=measure.count('1.0','end-1c','update','displaylines');lines=(count[0] if isinstance(count,tuple) else count or 0)+1
        if len(body)<=6000:
            cache[key]=lines
            while len(cache)>80:cache.popitem(last=False)
        height=lines*line_height+u(20);value.update(height=height,text_width=available,text_height=height-u(20),layout_measured=True)
        value['bubble'].configure(width=width,height=height);self.size_collapsed_row(value)

    def collapse_row(self,value):
        if not value.get('layout_measured'):return
        if value.get('collapsed_children'):return
        children=[(child,child.pack_info()) for child in value['outer'].winfo_children() if child.winfo_manager()=='pack']
        if not children:return
        value['collapsed_children']=children;value['outer'].pack_propagate(False);self.size_collapsed_row(value)
        for child,_ in children:child.pack_forget()
    def expand_row(self,value):
        children=value.pop('collapsed_children',None)
        if not children:return
        if value.get('estimated_layout'):self.remember_scroll_anchor()
        for child,options in children:child.pack(**options)
        value['outer'].pack_propagate(True)
        if value.get('estimated_layout'):
            value['layout_key']=None;self.completed_layout=None;self.queue_reflow()

    def thumbnail_ready(self):
        if not hasattr(self,'pending_top'):self.pending_top=max(0,self.canvas.canvasy(0))
        if not getattr(self,'media_layout_job',None):self.media_layout_job=self.after_idle(self.finish_media_layout)

    def finish_media_layout(self):
        self.media_layout_job=None;self.restore_scroll()

    def restore_scroll(self):
        if getattr(self,'restore_job',None):self.after_cancel(self.restore_job);self.restore_job=None
        region=self.canvas.bbox('all')
        if region:
            self.canvas.configure(scrollregion=region)
            anchor=getattr(self,'pending_anchor',None);self.pending_anchor=None
            if anchor and anchor[0] in self.bubbles:
                outer=self.bubbles[anchor[0]]['outer'];target=max(0,outer.winfo_y()+anchor[1]);self.canvas.yview_moveto(target/max(1,region[3]))
                if hasattr(self,'pending_top'):del self.pending_top
            elif hasattr(self,'pending_top'):
                self.canvas.yview_moveto(self.pending_top/max(1,region[3]));del self.pending_top
        self.refresh_visible()

    def see_message(self,message_id):
        value=self.bubbles.get(message_id)
        if value:
            self.update_idletasks();region=self.canvas.bbox('all')
            self.canvas.yview_moveto(value['outer'].winfo_y()/max(1,region[3]))
            value['bubble'].configure(highlightbackground=self.theme.color(ACCENT),highlightthickness=self.theme.u(2))

    def destroy(self):
        for name in ('render_job','cleanup_job','render_after_job','layout_step_job'):
            if getattr(self,name,None):self.after_cancel(getattr(self,name))
        if getattr(self,'media_layout_job',None):self.after_cancel(self.media_layout_job)
        if getattr(self,'restore_job',None):self.after_cancel(self.restore_job)
        if self.layout_job:self.after_cancel(self.layout_job)
        if getattr(self,'finish_job',None):self.after_cancel(self.finish_job)
        if getattr(self,'visibility_job',None):self.after_cancel(self.visibility_job)
        super().destroy()
