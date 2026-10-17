"""Compact model/power card; native variables and provider-supported efforts stay authoritative."""
import tkinter as tk
from tkinter import ttk
from .rounded import RoundedSurface,rounded_points
from .model_controls import AUTO_MODEL,EFFORT_LABELS


class PowerPopover:
    def __init__(self,panel,popup):
        self.panel=panel;self.app=panel.app;self.root=panel.root;self.popup=popup;self.alive=True;self.job=None;self.hide_job=None
        self.animation_job=None;self.phase=0;self.hovering=False
        t=self.app.theme;u=t.u;p=t.palette;outer=p['PAPER']
        try:popup.attributes('-transparentcolor','#ff00ff');outer='#ff00ff'
        except tk.TclError:pass
        popup.configure(background=outer);popup.overrideredirect(True);popup.resizable(False,False)
        self.surface=RoundedSurface(popup,t,outer,p['PAPER'],outline=p['LINE'],radius=14,padding=10);self.surface.pack(fill='both',expand=True)
        form=self.surface.content;form.columnconfigure(0,minsize=u(34));form.columnconfigure(1,weight=1);form.columnconfigure(2,minsize=u(34))
        panel.fast_button=self.app.icon(form,'fast','快速模式',lambda:panel.fast_mode.set(not panel.fast_mode.get()),'Quiet.TButton');panel.fast_button.grid(row=0,column=0,rowspan=2,sticky='n')
        panel.fast_button.toggled_color=lambda:'#c4b5fd' if self.app.theme.active_mode=='dark' else '#8b5cf6'
        panel.fast_button.tooltip_extra=lambda:self.app.tr('下一次发送起生效；服务端按账号和模型处理。')
        self.title=tk.Label(form,font=t.name,background=p['PAPER'],foreground=p['ACCENT']);self.title.grid(row=0,column=1,sticky='ew')
        self.model_button=ttk.Button(form,command=self.show_models,style='PowerModel.TButton',width=1);self.model_button.grid(row=1,column=1,sticky='ew')
        self.slider=tk.Canvas(form,height=u(36),width=u(250),background=p['PAPER'],highlightthickness=0,takefocus=1,cursor='hand2');self.slider.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(u(8),0))
        panel.power_slider=self.slider;panel.power_model_button=self.model_button
        self.slider.bind('<Button-1>',self.pointer);self.slider.bind('<B1-Motion>',self.pointer)
        self.slider.bind('<Left>',lambda _:self.step(-1));self.slider.bind('<Right>',lambda _:self.step(1));self.slider.bind('<Home>',lambda _:self.choose(0));self.slider.bind('<End>',lambda _:self.choose(len(self.levels())-1));self.slider.bind('<Configure>',lambda _:self.queue_refresh())
        self.slider.bind('<Enter>',lambda _:self.hover(True));self.slider.bind('<Leave>',lambda _:self.hover(False))
        self.menu=tk.Menu(popup,tearoff=False,borderwidth=0);self.traces=[]
        self.menu.bind('<Unmap>',self.schedule_hide,add='+')
        self.outside_binding=self.root.bind_all('<Button-1>',self.outside_click,add='+')
        for variable in (panel.model,panel.effort,panel.fast_mode):self.traces.append((variable,variable.trace_add('write',self.queue_refresh)))
        popup.bind('<FocusOut>',self.schedule_hide,add='+');popup.bind('<Escape>',self.escape);popup.bind('<Destroy>',self.cleanup,add='+')
        popup.bind('<Unmap>',self.stop_effect,add='+')
        self.refresh()

    def levels(self):return [label for label,value in self.panel.effort_ids.items() if value is not None] or [EFFORT_LABELS['']]
    def current_index(self):
        levels=self.levels();current=self.panel.effort.get()
        if current not in levels:current=next((label for label in levels if self.panel.effort_ids.get(label)==self.panel.selected_effort()),levels[0])
        return levels.index(current)
    def choose(self,index):
        if self.app.busy or not self.alive:return 'break'
        levels=self.levels();self.panel.effort.set(levels[max(0,min(len(levels)-1,index))]);self.queue_refresh();return 'break'
    def step(self,delta):return self.choose(self.current_index()+delta)
    def pointer(self,event):
        self.slider.focus_set();u=self.app.theme.u;width=max(u(30),self.slider.winfo_width()-u(24));position=max(0,min(1,(event.x-u(12))/width));self.choose(round(position*(len(self.levels())-1)));return 'break'
    def queue_refresh(self,*_):
        if not self.alive:return
        if self.job:self.root.after_cancel(self.job)
        self.job=self.root.after_idle(self.refresh)
    def refresh(self):
        self.job=None
        if not self.alive:return
        panel=self.panel;t=self.app.theme;p=t.palette;u=t.u;fast=panel.fast_mode.get();blue=('#c4b5fd' if t.active_mode=='dark' else '#8b5cf6') if fast else p['ACCENT']
        self.title.configure(text=self.app.tr(self.levels()[self.current_index()]),font=t.name,foreground=blue,background=p['PAPER'])
        model=panel.model.get().split(' · ')[0]
        if panel.model.get()==AUTO_MODEL:
            model=next((x['displayName'] for x in panel.model_catalog if x['model']==panel.selected_model()),self.app.tr(AUTO_MODEL))
        self.model_button.configure(text=t.elide(model,max(u(100),self.surface.winfo_width()-u(100)),True)+'  ›')
        self.slider.configure(background=p['PAPER']);self.slider.delete('all');width=max(u(60),self.slider.winfo_width());left=u(12);right=width-u(12);top=u(7);bottom=u(29);radius=u(11)
        self.slider.create_polygon(rounded_points(right-left,bottom-top,radius),fill=('#38284f' if t.active_mode=='dark' else '#ede9fe') if fast else p['SELECTED'],outline='',tags='track');self.slider.move('track',left,top)
        steps=len(self.levels());index=self.current_index();x=left+(right-left)*index/max(1,steps-1)
        if index:
            self.slider.create_polygon(rounded_points(max(u(22),x-left),bottom-top,radius),fill=blue,outline='',tags='fill');self.slider.move('fill',left,top)
        for number in range(steps):
            dot=left+(right-left)*number/max(1,steps-1);self.slider.create_oval(dot-u(1),u(17),dot+u(1),u(19),fill='#c2d5ff' if number<=index else p['SECONDARY'],outline='')
        self.slider.create_oval(x-u(12),u(6),x+u(12),u(30),fill=p['PAPER'],outline=p['LINE'],width=u(1),tags='thumb')
        self.paint_effect()
        panel.fast_button.toggled=panel.fast_mode.get();panel.fast_button.refresh_icon()
        if fast and self.popup.winfo_ismapped():self.start_effect()
        elif getattr(self,'animation_fast',False):self.stop_effect();self.animation_fast=False;self.paint_effect()
    def hover(self,value):self.hovering=value;self.paint_effect()
    def paint_effect(self):
        if not self.alive:return
        self.slider.delete('sparkle');t=self.app.theme;u=t.u;reduced=self.app.ui_settings['reduce_motion']
        left=u(12);right=max(u(60),self.slider.winfo_width())-u(12)
        index=self.current_index();x=left+(right-left)*index/max(1,len(self.levels())-1)
        if self.panel.fast_mode.get():
            span=max(u(8),right-left-u(12));center=(left+right)/2 if reduced else left+u(6)+span*self.phase
            color='#e9ddff' if t.active_mode=='dark' else '#c4b5fd'
            if reduced:
                import math
                blend=(1+math.sin(self.phase*math.tau))/2
                low=(139,92,246) if t.active_mode!='dark' else (166,138,235);high=(196,181,253)
                color='#'+''.join(f'{round(a+(b-a)*blend):02x}' for a,b in zip(low,high))
                self.slider.itemconfigure('fill',fill=color)
            self.slider.create_line(max(left+u(4),center-u(22)),u(18),min(right-u(4),center+u(22)),u(18),fill=color,width=u(5),tags=('sparkle','fast_pulse' if reduced else 'fast_flow'))
            self.slider.create_line(max(left+u(4),center-u(8)),u(18),min(right-u(4),center+u(8)),u(18),fill='#ffffff',width=u(2),tags=('sparkle','fast_pulse' if reduced else 'fast_flow'))
        if self.hovering:
            self.slider.create_oval(x-u(13),u(5),x+u(13),u(31),outline='#759ce1' if t.active_mode=='dark' else '#bad2ff',width=u(2),tags='sparkle')
        span=x-left-u(18)
        if span>u(8) and not reduced:
            for number in range(6):
                drift=(self.phase+number*.173)%1;px=left+u(5)+span*drift;py=u(13+(number*7)%9)
                color='#f5f9ff' if (self.phase+number*.13)%1<.45 else '#bfd6ff';radius=u(1)
                self.slider.create_oval(px-radius,py-radius,px+radius,py+radius,fill=color,outline='',tags='sparkle')
                if number%3==0:
                    self.slider.create_line(px-u(2),py,px+u(2),py,fill=color,tags='sparkle')
                    self.slider.create_line(px,py-u(2),px,py+u(2),fill=color,tags='sparkle')
        if self.slider.find_withtag('thumb'):self.slider.tag_lower('sparkle','thumb')
    def start_effect(self):
        self.stop_effect();self.animation_fast=self.panel.fast_mode.get()
        if self.app.ui_settings['reduce_motion'] and not self.panel.fast_mode.get():self.paint_effect();return
        self.animation_job=self.root.after_idle(self.animate)
    def animate(self):
        self.animation_job=None
        if not self.alive or not self.popup.winfo_ismapped() or self.app.ui_settings['reduce_motion'] and not self.panel.fast_mode.get():return
        self.phase=(self.phase+(.045 if self.panel.fast_mode.get() else .025))%1;self.paint_effect()
        self.animation_job=self.root.after(120 if self.app.ui_settings['reduce_motion'] else 33 if self.panel.fast_mode.get() else 80,self.animate)
    def stop_effect(self,event=None):
        if event is not None and event.widget is not self.popup:return
        if self.animation_job:self.root.after_cancel(self.animation_job);self.animation_job=None
    def show_models(self):
        if self.app.busy:return
        t=self.app.theme;p=t.palette;self.menu.delete(0,'end');self.menu.configure(font=t.body,background=p['PAPER'],foreground=p['INK'],activebackground=p['SELECTED'],activeforeground=p['INK'])
        for label in (AUTO_MODEL,*self.panel.model_ids):
            text=self.app.tr(label) if label==AUTO_MODEL else label.split(' · ')[0]
            if label!=AUTO_MODEL and sum(x.split(' · ')[0]==text for x in self.panel.model_ids)>1:text=label
            def select(value=label):self.panel.model.set(value);self.popup.after_idle(self.popup.focus_set)
            self.menu.add_radiobutton(label=text,variable=self.panel.model,value=label,command=select)
        self.menu.add_separator();self.menu.add_command(label=self.app.tr('刷新模型列表'),command=self.panel.refresh_models,state='disabled' if self.panel.models_button.instate(['disabled']) else 'normal')
        self.menu.tk_popup(self.model_button.winfo_rootx(),self.model_button.winfo_rooty()+self.model_button.winfo_height())
    def show(self):
        if self.app.busy:return
        t=self.app.theme;u=t.u;width=u(max(280,min(340,t.text_size*12+100)))
        t.style.configure('PowerModel.TButton',font=t.small,padding=(u(2),0),foreground=t.palette['SECONDARY'])
        self.surface.configure(width=width);t.apply_tree(self.popup);self.app.localizer.apply(self.popup,());self.refresh();self.popup.update_idletasks()
        height=max(u(108),self.surface.content.winfo_reqheight()+u(20));anchor=self.panel.parameters_button
        x=max(0,min(anchor.winfo_rootx(),self.popup.winfo_screenwidth()-width-u(8)));y=max(u(8),anchor.winfo_rooty()-height-u(8))
        self.popup.geometry(f'{width}x{height}+{x}+{y}');self.popup.deiconify();self.popup.lift();self.popup.focus_set();self.queue_refresh();self.start_effect()
    def schedule_hide(self,event=None):
        if not self.alive:return
        if self.hide_job:self.root.after_cancel(self.hide_job)
        self.hide_job=self.root.after(80,self.hide_if_outside)
    def outside_click(self,event):
        if not self.alive or not self.popup.winfo_ismapped() or self.menu.winfo_ismapped():return
        x,y=self.popup.winfo_rootx(),self.popup.winfo_rooty()
        if not (x<=event.x_root<x+self.popup.winfo_width() and y<=event.y_root<y+self.popup.winfo_height()):self.popup.withdraw()
    def hide_if_outside(self):
        self.hide_job=None
        if not self.alive or self.menu.winfo_ismapped():return
        focused=str(self.root.tk.call('focus'));name=str(self.popup)
        if not (focused==name or focused.startswith(name+'.')):self.popup.withdraw()
    def escape(self,event=None):self.popup.withdraw();self.panel.parameters_button.focus_set();return 'break'
    def cleanup(self,event):
        if event.widget is not self.popup:return
        self.stop_effect()
        self.alive=False
        for job in (self.job,self.hide_job):
            if job:self.root.after_cancel(job)
        for variable,token in self.traces:
            try:variable.trace_remove('write',token)
            except tk.TclError:pass
        try:
            script=str(self.root.tk.call('bind','all','<Button-1>'))
            prefix='if {"['+self.outside_binding+' '
            self.root.tk.call('bind','all','<Button-1>','\n'.join(line for line in script.splitlines() if not line.startswith(prefix)))
            self.root.deletecommand(self.outside_binding)
        except tk.TclError:pass
