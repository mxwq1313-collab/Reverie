"""Inline disclosure for registered WeChat forwards; never changes archived XML."""
import tkinter as tk
import math,time
from tkinter import ttk


class ForwardMessage(tk.Frame):
    PAGE = 20
    def __init__(self, timeline, parent, row, document):
        self.timeline=timeline;self.theme=timeline.theme;self.row=row
        self.records=document['items'];self.total=document['total'];self.expanded=False
        self.render_job=None;self.resize_job=None;self.rendered=[];self.target=0
        self.font_key=None;self.fit_key=None;self.measure=None;self.measure_cache={};self.needs_fit=False;u=self.theme.u;p=self.theme.palette
        super().__init__(parent,background=p['PAPER'],highlightbackground=p['LINE'],highlightthickness=u(1),padx=u(12),pady=u(10))
        own=row.get('sender_id')==getattr(timeline.app,'owner_id',None)
        self.pack(fill='x',padx=(u(40),0) if own else (0,u(40)),pady=(u(6),u(4)))
        self.heading=ttk.Button(self,text=f'聊天记录 · {self.total} 条   ▸ 展开',command=self.toggle,style='Quiet.TButton')
        self.heading._keep_caption=True;self.heading.pack(fill='x')
        self.preview=tk.Label(self,text='\n'.join(x['name']+'：'+x['text'].replace('\n',' ')[:80] for x in self.records[:2]),font=self.theme.small,background=p['PAPER'],foreground=p['SECONDARY'],anchor='w',justify='left',wraplength=u(350))
        self.preview._raw_text=True;self.preview.pack(fill='x',pady=(u(7),0))
        self.body=tk.Frame(self,background=p['PAPER']);self.actions=ttk.Frame(self)
        self.more=ttk.Button(self.actions,text='再显示20条',command=self.more_records,style='Quiet.TButton');self.more.pack(side='left')
        self.fold=ttk.Button(self.actions,text='收起记录',command=self.collapse,style='Quiet.TButton');self.fold.pack(side='right')
        self.count=tk.Label(self,background=p['PAPER'],foreground=p['SECONDARY'],font=self.theme.small,anchor='w')
        self.menu=tk.Menu(self,tearoff=False)
        self.menu.add_command(label='复制转发文字',command=self.copy_text)
        self.menu.add_command(label='复制这条原文',command=lambda:timeline.copy_raw(row.get('content')))
        for widget in (self,self.heading,self.preview):widget.bind('<Button-3>',lambda event:self.menu.tk_popup(event.x_root,event.y_root))
        self.bind('<Configure>',self.schedule_fit,add='+');self.bind('<Map>',lambda _:self.schedule_fit(),add='+');self.bind('<Destroy>',self.destroyed,add='+')
        timeline.theme.apply_tree(self);timeline.theme.wheel_router.attach(self)

    def changed(self,folding=False):
        view=self.timeline
        if not hasattr(view,'pending_top'):
            top=max(0,view.canvas.canvasy(0))
            view.pending_top=min(top,self.master.winfo_y()) if folding else top
        view.thumbnail_ready()

    def toggle(self):
        if self.expanded:return self.collapse()
        self.changed();self.expanded=True;self.preview.pack_forget()
        self.body.pack(fill='x',pady=self.theme.u(8));self.count.pack(fill='x',pady=self.theme.u(5));self.actions.pack(fill='x')
        self.heading.configure(text=f'聊天记录 · {self.total} 条   ▾ 收起')
        self.target=min(self.PAGE,len(self.records));self.render_batch()
        self.timeline.app.status.set(f'已展开合并消息，共 {self.total} 条。')

    def collapse(self):
        if not self.expanded:return
        self.changed(folding=True);self.expanded=False
        for name in ('render_job','resize_job'):
            job=getattr(self,name)
            if job:self.after_cancel(job);setattr(self,name,None)
        for child in self.body.winfo_children():child.destroy()
        self.release_measure();self.rendered=[];self.target=0;self.body.pack_forget();self.actions.pack_forget();self.count.pack_forget()
        self.preview.pack(fill='x',pady=(self.theme.u(7),0));self.heading.configure(text=f'聊天记录 · {self.total} 条   ▸ 展开');self.heading.focus_set()
        self.timeline.app.status.set('合并消息已收起。')

    def more_records(self):
        if self.render_job:self.after_cancel(self.render_job);self.render_job=None
        self.changed();self.target=min(len(self.records),self.target+self.PAGE);self.render_batch()

    def render_batch(self):
        self.render_job=None
        if not self.expanded:return
        u=self.theme.u;p=self.theme.palette;start=len(self.rendered)
        for item in self.records[start:min(start+5,self.target)]:
            frame=tk.Frame(self.body,background=p['CANVAS'],padx=u(10),pady=u(8));frame.pack(fill='x',pady=(0,u(8)))
            available=max(u(70),self.winfo_width()-u(64))
            lines=sum(max(1,math.ceil(self.theme.font.measure(line)/available)) for line in item['text'].split('\n'))
            estimated=(lines+1)*(self.theme.font.metrics('linespace')+u(4))+u(60)
            frame._forward_virtual=True;frame._forward_measured=None;frame._forward_item=item
            frame.configure(height=estimated);frame.pack_propagate(False)
            self.rendered.append((frame,None,None))
        self.count.configure(text=f'已显示 {len(self.rendered)} / {self.total} 条'+(' · 最多预览100条，完整内容保留在原文中' if self.total>len(self.records) else ''))
        self.more.configure(state='normal' if len(self.rendered)<len(self.records) else 'disabled')
        self.schedule_fit()
        if len(self.rendered)<self.target:self.render_job=self.after(1,self.render_batch)
        self.changed()

    def schedule_fit(self,event=None):
        if event is not None and event.widget is not self:return
        key=(self.winfo_width(),self.theme.generation,len(self.rendered))
        if event is not None and key==self.fit_key:return
        self.fit_key=key
        if self.resize_job:self.after_cancel(self.resize_job)
        self.resize_job=self.after(40,self.fit)

    def release_measure(self):
        if self.measure is not None:
            try:
                if self.measure.winfo_exists():self.measure.destroy()
            except tk.TclError:pass
        self.measure=None;self.measure_cache.clear()

    def measured_lines(self,item,text,width):
        """Never force Tk metric synchronization on clipped/uninitialized children."""
        from .inline_emojis import render_inline
        u=self.theme.u
        key=(item,width,self.theme.body,self.theme.generation)
        if key in self.measure_cache:return self.measure_cache[key]
        if self.measure is None:
            self.measure=tk.Text(self.timeline.canvas,wrap='word',borderwidth=0,highlightthickness=0,padx=u(9),pady=u(8),takefocus=0,exportselection=False)
        measure=self.measure
        measure.configure(font=self.theme.body,spacing1=u(1),spacing3=u(3))
        measure.place(x=-30000,y=0,width=width,height=max(u(20),self.theme.font.metrics('linespace')))
        if measure.winfo_width()!=width or not measure.winfo_ismapped():return None
        if not measure.winfo_ismapped() or measure.winfo_width()<20:return None
        measure.delete('1.0','end');measure.insert('1.0',item);render_inline(measure,self.theme)
        count=measure.count('1.0','end-1c','update','displaylines');lines=(count[0] if isinstance(count,tuple) else count or 0)+1
        measure.place_forget()
        self.measure_cache[key]=lines
        while len(self.measure_cache)>128:self.measure_cache.pop(next(iter(self.measure_cache)))
        return lines

    def realize(self,index):
        frame,label,text=self.rendered[index]
        if text is not None:return frame,label,text
        item=frame._forward_item;u=self.theme.u;p=self.theme.palette
        label=tk.Label(frame,text=item['name']+(' · '+item['time'] if item['time'] else ''),background=p['CANVAS'],foreground=p['SECONDARY'],font=self.theme.small,anchor='w',justify='left',wraplength=u(350));label._raw_text=True
        label.pack(fill='x',pady=(0,u(5)))
        holder=tk.Frame(frame,background=p['PAPER'],height=u(48));frame._text_holder=holder
        text=tk.Text(holder,font=self.theme.body,wrap='word',height=1,width=1,background=p['PAPER'],foreground=p['INK'],borderwidth=0,highlightthickness=0,padx=u(9),pady=u(8),spacing1=u(1),spacing3=u(3),cursor='xterm')
        holder.pack(fill='x');text.place(x=0,y=0,width=max(u(100),frame.winfo_width()-u(20)),height=u(48));text.insert('1.0',item['text'])
        frame._media_frame=None
        from .inline_emojis import render_inline
        render_inline(text,self.theme);text.configure(state='disabled');text._forward_font=self.theme.body
        text.bind('<Control-c>',lambda _,widget=text:self.timeline.copy_selection(widget))
        text.bind('<Control-a>',lambda _,widget=text:self.timeline.select_all(widget))
        menu=tk.Menu(text,tearoff=False);menu.add_command(label='复制选中文字',command=lambda widget=text:self.timeline.copy_selection(widget));menu.add_command(label='复制这条消息',command=lambda value=item['text']:self.timeline.copy_raw(value))
        text.bind('<Button-3>',lambda event:menu.tk_popup(event.x_root,event.y_root))
        self.rendered[index]=(frame,label,text);self.theme.apply_tree(frame);self.theme.wheel_router.attach(frame)
        if item.get('media') is not None:
            text.configure(state='normal');text.delete('1.0','end');text.insert('1.0','图片加载中…');text.configure(state='disabled')
            app=self.timeline.app
            from .forward_image_service import ForwardImageService
            if not hasattr(app,'forward_image_service'):app.forward_image_service=ForwardImageService(app)
            if item['media']['images']:app.forward_image_service.submit(self,index,item['media'])
            else:self.media_ready(index,None)

        return frame,label,text

    def update_visible(self,schedule=True):
        if not self.expanded:return
        view=self.timeline
        if not view.canvas.winfo_ismapped() or view.app.current_page!='聊天归档':return
        u=self.theme.u;top=view.canvas.canvasy(0)-u(80);bottom=top+view.canvas.winfo_height()+u(160)
        origin=self.master.winfo_y()+self.winfo_y()+self.body.winfo_y()
        width=max(u(100),self.winfo_width()-(2*u(1)+2*u(12)+2*u(10)))
        key=(width,self.theme.body,self.theme.generation);needs=False
        for index,(frame,label,text) in enumerate(self.rendered):
            if frame.winfo_width()<20 or frame.winfo_height()<=1:continue
            first=origin+frame.winfo_y();last=first+max(frame.winfo_height(),frame.winfo_reqheight())
            visible=last>top and first<bottom
            if visible:
                if frame._forward_virtual:
                    frame,label,text=self.realize(index)
                    label.pack(fill='x',pady=(0,u(5)))
                    if getattr(frame,'_media_frame',None):frame._media_frame.pack(fill='x')
                    else:frame._text_holder.pack(fill='x')
                    frame._forward_virtual=False
                if frame._forward_measured!=key:needs=True
            elif not frame._forward_virtual:
                frame.configure(height=max(frame.winfo_height(),frame.winfo_reqheight()));frame.pack_propagate(False)
                label.pack_forget();frame._text_holder.pack_forget()
                if getattr(frame,'_media_frame',None):frame._media_frame.pack_forget()
                frame._forward_virtual=True
        if needs and schedule and not self.resize_job:self.schedule_fit()

    def fit(self):
        self.resize_job=None;u=self.theme.u;width=max(u(100),self.winfo_width()-u(30))
        if getattr(self,'preview_key',None)!=(width,self.theme.small):
            self.preview.configure(wraplength=width,font=self.theme.small);self.preview_key=(width,self.theme.small)
        if not self.expanded:return
        if not self.timeline.canvas.winfo_ismapped() or self.timeline.app.current_page!='聊天归档':
            self.needs_fit=True;return
        if time.monotonic()<getattr(self.timeline,'resizing_until',0):
            self.resize_job=self.after(80,self.fit);return
        if not self.winfo_exists() or not self.expanded:return
        self.needs_fit=False;self.update_visible(schedule=False)
        expected=max(u(100),self.winfo_width()-(2*u(1)+2*u(12)+2*u(10)))
        key=(expected,self.theme.body,self.theme.generation)
        started=time.perf_counter();pending=False;changed=False
        for frame,label,text in self.rendered:
            if frame._forward_virtual or frame._forward_measured==key:continue
            if getattr(frame,'_media_frame',None):
                frame.pack_propagate(True);frame._forward_measured=key;continue
            if time.perf_counter()-started>.004:pending=True;break
            label.configure(wraplength=max(u(80),width-u(20)),font=self.theme.small)
            from .inline_emojis import resize_inline
            resize_inline(text,self.theme)
            if text._forward_font!=self.theme.body:text.configure(font=self.theme.body);text._forward_font=self.theme.body
            lines=self.measured_lines(text.get('1.0','end-1c'),text,expected)
            if lines is None:pending=True;continue
            text.configure(height=lines+1)
            pixel_height=max(u(20),text.winfo_reqheight())
            frame._text_holder.configure(height=pixel_height);text.place_configure(width=expected,height=pixel_height)
            frame.configure(height=label.winfo_reqheight()+pixel_height+u(21));frame.pack_propagate(True)
            frame._forward_measured=key;changed=True
        if pending:self.resize_job=self.after(16,self.fit)
        if changed:self.changed()

    def media_ready(self,index,item):
        if not self.expanded or index>=len(self.rendered):return
        frame,label,text=self.rendered[index]
        if text is None or not text.winfo_exists():return
        if item is None:
            text.configure(state='normal');text.delete('1.0','end');text.insert('1.0','图片未取得 · 请在微信下载图片后重新读取此会话');text.configure(state='disabled')
            frame._forward_measured=None;self.schedule_fit();return
        frame._text_holder.pack_forget()
        from .media_widgets import attachment_content
        media=tk.Frame(frame,background=self.theme.palette['CANVAS']);frame._media_frame=media
        if not frame._forward_virtual:media.pack(fill='x')
        row={**self.row,'msg_type':'image','content':'[图片]','attachments':[item]}
        attachment_content(self.timeline,media,row,thumbnail_owner=self.master)
        frame._forward_measured=None;frame.pack_propagate(True);self.changed();self.schedule_fit()

    def copy_text(self):
        from ..message_content import forwarded_text
        self.timeline.copy_raw(forwarded_text(self.row.get('content'),limit=100));self.timeline.app.status.set('转发文字已复制；完整XML可从原文菜单复制。')

    def destroyed(self,event):
        if event.widget is not self:return
        self.release_measure()
        for name in ('render_job','resize_job'):
            job=getattr(self,name,None)
            if job:self.after_cancel(job);setattr(self,name,None)
