"""浅色工作台主题；逻辑像素与 Tk 字体像素明确分开。"""
import tkinter.font as font
from tkinter import ttk,TclError
from .rounded import rounded_image
from .scrolling import WheelRouter

PAPER='#ffffff'
CANVAS='#fafafa'
SIDEBAR='#f4f4f5'
INK='#202124'
SECONDARY='#5f6368'
ACCENT='#262626'
SELECTED='#e8e9eb'
OWN='#edf3f8'
LINE='#dedee1'
HOVER='#f0f0f2'
DISABLED='#ececef'
MUTED='#707078'

LIGHT={key:globals()[key] for key in ('PAPER','CANVAS','SIDEBAR','INK','SECONDARY','ACCENT','SELECTED','OWN','LINE','HOVER','DISABLED','MUTED')}
LIGHT.update(AI='#f6f8fc',PRIMARY_HOVER='#404040',PRIMARY_PRESSED='#111111')
LIGHT['DANGER']='#a53030'
DARK=dict(zip(('PAPER','CANVAS','SIDEBAR','INK','SECONDARY','ACCENT','SELECTED','OWN','LINE','HOVER','DISABLED','MUTED'),
              ('#1f2023','#17181b','#202226','#e8eaf0','#a4a8b3','#ccd9f4','#353a45','#27364a','#363941','#2b2f37','#2a2c32','#7b8190')))
DARK.update(AI='#1a202b',PRIMARY_HOVER='#b7c8ed',PRIMARY_PRESSED='#a0b5e2')
DARK['DANGER']='#ffb4ab'
def tinted(paper,canvas,sidebar,accent,selected,own,line,hover,ai):
    palette=dict(LIGHT);palette.update(PAPER=paper,CANVAS=canvas,SIDEBAR=sidebar,ACCENT=accent,SELECTED=selected,OWN=own,LINE=line,HOVER=hover,AI=ai,PRIMARY_HOVER=accent,PRIMARY_PRESSED=accent)
    return palette

PALETTES={'light':LIGHT,'dark':DARK,
    'sand':tinted('#fffdfa','#faf7f2','#f2ebe1','#805330','#ece0d0','#f3e8d9','#ddd1c2','#f5eddf','#f7f0e5'),
    'blue':tinted('#fcfdff','#f4f7fc','#eaf0f8','#345d8e','#dce7f6','#e6eefb','#cfd9e9','#edf3fc','#eef4fd'),
    'green':tinted('#fcfefc','#f4f8f5','#e9f1ec','#32664d','#dcebe1','#e4f1e9','#ccdcd2','#edf6f0','#eef7f2'),
    'violet':tinted('#fefcff','#f8f5fc','#f0eaf7','#70528f','#e7ddf2','#eee5f8','#dcd0e8','#f4edfb','#f5effc')}
COLOR_ROLES={}
for _palette in PALETTES.values():
    for _key,_color in _palette.items():COLOR_ROLES.setdefault(_color,_key)



class Theme:
    def __init__(self,root,text_size=15,family='',mode='light',language='zh_CN',wheel_speed=48):
        self.root=root;self.scale=max(.9,float(root.tk.call('tk','scaling'))/(96/72))
        self.mode=mode;self.language=language;self.active_mode=self.resolved_mode();self.palette=dict(PALETTES[self.active_mode]);self.generation=0
        self.style=ttk.Style(root);self.images=[];self.action_maps_closed=False
        def mapped(event):
            if self.action_maps_closed:return
            try:
                self.prepare(event.widget)
                self.scope_font(event.widget,event.widget.winfo_class())
                from .symbol_actions import symbolize
                symbolize(event.widget,self)
            except (AttributeError,TclError):pass
        self.action_map_job=root.bind_all('<Map>',mapped,add='+')
        self.wheel_router=WheelRouter(root,self.scale);self.wheel_router.pixels=self.u(wheel_speed)
        self.set_fonts(text_size,family,True);self.configure_styles()

    def resolved_mode(self):
        if self.mode!='system':return self.mode
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
                return 'light' if winreg.QueryValueEx(key,'AppsUseLightTheme')[0] else 'dark'
        except (ImportError,OSError):return 'light'

    def set_fonts(self,size,family,initial=False):
        if initial:self.available_fonts=sorted(name for name in set(font.families(self.root)) if not name.startswith('@'))
        families=set(self.available_fonts)
        self.family=family if family in families else next((name for name in ('Microsoft YaHei UI','Microsoft YaHei','Segoe UI','Arial') if name in families),'TkDefaultFont')
        self.text_size=size;self.body=(self.family,-self.u(size));self.small=(self.family,-self.u(max(12,round(size*.8))))
        self.title=(self.family,-self.u(max(20,size+5)),'bold');self.name=(self.family,-self.u(max(14,size-1)),'bold')
        self.section=(self.family,-self.u(max(18,size+3)),'bold')
        if initial:
            self.font=font.Font(self.root,family=self.family,size=-self.u(size))
            self.small_font=font.Font(self.root,family=self.family,size=self.small[1])
            self.section_font=font.Font(self.root,font=self.section)
        else:
            self.font.configure(family=self.family,size=-self.u(size));self.small_font.configure(family=self.family,size=self.small[1]);self.section_font.configure(family=self.family,size=self.section[1],weight='bold')

    @property
    def control_height(self):return self.font.metrics('linespace')+self.u(14)

    def color(self,value):
        value=str(value).lower();value='#ffffff' if value in ('white','#fff') else value
        role=COLOR_ROLES.get(value)
        if role:return self.palette[role]
        special={'#ffe39a':'#6e5521' if self.active_mode=='dark' else '#ffe39a','#6e5521':'#6e5521' if self.active_mode=='dark' else '#ffe39a'}
        return special.get(value,value)

    @property
    def scroll_color(self):return '#50545d' if self.active_mode=='dark' else '#d5d9e0'
    @property
    def scroll_hover(self):return '#818794' if self.active_mode=='dark' else '#aeb7c4'

    def configure_styles(self,rebuild_images=True):
        root=self.root
        PAPER,CANVAS,SIDEBAR,INK,SECONDARY,ACCENT,SELECTED,OWN,LINE,HOVER,DISABLED,MUTED=(self.palette[key] for key in ('PAPER','CANVAS','SIDEBAR','INK','SECONDARY','ACCENT','SELECTED','OWN','LINE','HOVER','DISABLED','MUTED'))
        if self.style.theme_use()!='clam':self.style.theme_use('clam')
        self.style.configure('.',font=self.body,background=PAPER,foreground=INK)
        self.style.configure('TFrame',background=PAPER)
        self.style.configure('Card.TFrame',background=PAPER,borderwidth=1,relief='solid',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
        self.style.configure('Canvas.TFrame',background=CANVAS)
        self.style.configure('TLabel',background=PAPER,foreground=INK)
        self.style.configure('Hint.TLabel',foreground=SECONDARY,font=self.small)
        self.style.configure('Copilot.TButton',font=self.small)
        self.style.configure('Ai.TFrame',background=self.palette['AI'])
        self.style.configure('Ai.TLabel',background=self.palette['AI'],foreground=INK)
        self.style.configure('Ai.Hint.TLabel',background=self.palette['AI'],foreground=SECONDARY,font=self.small)
        self.style.configure('Title.TLabel',font=self.title)
        self.style.configure('TButton',padding=(self.u(12),self.u(7)),background=PAPER,foreground=INK,borderwidth=0,relief='flat',bordercolor=LINE,lightcolor=PAPER,darkcolor=PAPER,focuscolor=ACCENT)
        self.style.map('TButton',background=[('disabled',DISABLED),('pressed',SELECTED),('active',HOVER)],foreground=[('disabled',MUTED)],bordercolor=[('focus',INK),('active',LINE)])
        self.style.configure('Primary.TButton',background=ACCENT,foreground=PAPER,borderwidth=0)
        self.style.map('Primary.TButton',background=[('disabled',DISABLED),('pressed','#111111'),('active','#404040')],foreground=[('disabled',MUTED)],lightcolor=[('!disabled',ACCENT)],darkcolor=[('!disabled',ACCENT)])
        self.style.configure('Quiet.TButton',borderwidth=0,foreground=SECONDARY)
        self.style.configure('Disclosure.TButton',font=self.small,anchor='w',padding=(self.u(6),self.u(5)),borderwidth=0,foreground=SECONDARY)
        self.style.configure('Danger.TButton',foreground=self.palette['DANGER'])
        self.style.configure('Composer.TFrame',background=PAPER,borderwidth=1,relief='solid',bordercolor=LINE,lightcolor=LINE,darkcolor=LINE)
        self.style.configure('TEntry',padding=(self.u(12),self.u(7)),fieldbackground=CANVAS,borderwidth=0,bordercolor=LINE,lightcolor=PAPER,darkcolor=PAPER,insertcolor=INK)
        self.style.map('TEntry',bordercolor=[('focus',INK)],fieldbackground=[('readonly',CANVAS),('disabled',DISABLED)])
        self.style.configure('TCombobox',padding=(self.u(12),self.u(7)),background=PAPER,fieldbackground=CANVAS,borderwidth=0,arrowcolor=SECONDARY,bordercolor=LINE,lightcolor=PAPER,darkcolor=PAPER,arrowsize=self.u(12))
        self.style.map('TCombobox',fieldbackground=[('readonly',CANVAS),('disabled',DISABLED)],background=[('active',HOVER),('readonly',CANVAS)],foreground=[('disabled',MUTED),('readonly',INK)],selectbackground=[('readonly',SELECTED)],selectforeground=[('readonly',INK)],bordercolor=[('focus',INK)])
        self.style.configure('TCheckbutton',background=PAPER,foreground=INK)
        self.style.map('TCheckbutton',background=[('active',PAPER)])
        self.style.configure('TSeparator',background=LINE)
        self.style.configure('Vertical.TScrollbar',background='#c9c9cf',troughcolor=CANVAS,borderwidth=0,arrowsize=self.u(11),relief='flat')
        self.style.layout('Vertical.TScrollbar',[('Vertical.Scrollbar.trough',{'sticky':'ns','children':[('Vertical.Scrollbar.thumb',{'expand':'1','sticky':'nswe'})]})])
        self.style.map('Vertical.TScrollbar',background=[('active','#aaaab2'),('pressed','#8a8a94')])
        self.style.configure('Horizontal.TScrollbar',background='#c9c9cf',troughcolor=CANVAS,borderwidth=0,arrowsize=self.u(11),relief='flat')
        self.style.layout('Horizontal.TScrollbar',[('Horizontal.Scrollbar.trough',{'sticky':'ew','children':[('Horizontal.Scrollbar.thumb',{'expand':'1','sticky':'nswe'})]})])
        self.style.configure('Light.Horizontal.TProgressbar',thickness=self.u(3),background=SELECTED,troughcolor=PAPER,borderwidth=0,bordercolor=PAPER,lightcolor=PAPER,darkcolor=PAPER)
        self.style.configure('TNotebook',background=PAPER,borderwidth=0,bordercolor=PAPER,lightcolor=PAPER,darkcolor=PAPER)
        self.style.configure('TNotebook.Tab',padding=(self.u(17),self.u(9)),background=CANVAS,borderwidth=0)
        self.style.map('TNotebook.Tab',background=[('selected',PAPER)],foreground=[('selected',ACCENT)])
        self.style.configure('Treeview',font=self.body,rowheight=self.u(max(34,self.text_size+18)),background=PAPER,fieldbackground=PAPER,borderwidth=0,bordercolor=PAPER,lightcolor=PAPER,darkcolor=PAPER)
        self.style.configure('Treeview.Heading',font=self.name,background=CANVAS,relief='flat')
        self.style.map('Treeview',background=[('selected',SELECTED)],foreground=[('selected',INK)])
        root.option_add('*TCombobox*Listbox.font',self.body)
        root.option_add('*TCombobox*Listbox.background',PAPER)
        root.option_add('*TCombobox*Listbox.foreground',INK)
        root.option_add('*TCombobox*Listbox.selectBackground',SELECTED)
        root.option_add('*TCombobox*Listbox.selectForeground',INK)
        if rebuild_images:self.rounded_controls()

    def configure_font_styles(self):
        self.root.option_add('*TCombobox*Listbox.font',self.body)

    def scope_font(self,widget,kind):
        if kind=='TButton' and hasattr(self,'feedback'):self.feedback.attach(widget)
        if kind=='TCombobox':
            from .control_style import prepare_combobox
            prepare_combobox(widget,self)
            return
        if kind=='TLabel':
            style=str(widget.cget('style'))
            if not widget.cget('font'):
                widget._auto_theme_font='title' if 'Title' in style else 'small' if 'Hint' in style else 'body'
            if hasattr(widget,'_auto_theme_font'):
                target=getattr(self,widget._auto_theme_font)
                if tuple(self.root.tk.splitlist(str(widget.cget('font'))))!=tuple(map(str,target)):widget.configure(font=target)
            return
        if kind not in ('TButton','TCheckbutton','Treeview','TNotebook'):return
        if kind=='TButton' and not str(widget.cget('cursor')):widget.configure(cursor='hand2')
        current=str(widget.cget('style')) or kind
        base=getattr(widget,'_font_style_base',current) if current==getattr(widget,'_font_style_name',None) else current
        target=self.name if 'SelectedNav' in base else self.small if any(x in base for x in ('Hint','Copilot','Disclosure','PowerChip','PowerModel')) else self.body
        cache=getattr(self,'_scoped_fonts',None)
        if cache is None:self._scoped_fonts=cache={}
        key=(base,target,kind)
        if key not in cache:
            for size in range(12,25):
                logical=max(14,size-1) if 'SelectedNav' in base else max(12,round(size*.8)) if any(x in base for x in ('Hint','Copilot','Disclosure','PowerChip','PowerModel')) else size
                candidate=(self.family,-self.u(logical),'bold') if 'SelectedNav' in base else (self.family,-self.u(logical))
                candidate_key=(base,candidate,kind)
                if candidate_key in cache:continue
                name='Font'+str(len(cache))+'.'+base;values={'font':candidate}
                if kind=='Treeview':values['rowheight']=self.u(max(34,size+18))
                self.style.configure(name,**values)
                if kind=='Treeview':self.style.configure(name+'.Heading',font=(self.family,-self.u(max(14,size-1)),'bold'))
                if kind=='TNotebook':self.style.configure(name+'.Tab',font=(self.family,-self.u(size)))
                cache[candidate_key]=name
        name=cache[key];widget._font_style_base=base;widget._font_style_name=name
        if current!=name:widget.configure(style=name)

    def rounded_controls(self):
        """Keep native ttk behavior while replacing rectangular control borders."""
        u=self.u;style=self.style;self.images=[];self.generation+=1;suffix=str(self.generation)
        PAPER,CANVAS,SIDEBAR,INK,SECONDARY,ACCENT,SELECTED,OWN,LINE,HOVER,DISABLED,MUTED=(self.palette[key] for key in ('PAPER','CANVAS','SIDEBAR','INK','SECONDARY','ACCENT','SELECTED','OWN','LINE','HOVER','DISABLED','MUTED'))
        style.configure('TButton',width=-1)
        def element(name,fill,outer=PAPER,border=None,radius=0,states=(),mark=None):
            size=u(radius*2+8);edge=u(radius)
            normal=rounded_image(self.root,size,edge,fill,border,outer);self.images.append(normal)
            if mark=='line':normal.put(LINE,to=(0,size-u(1),size,size))
            if mark=='left':normal.put(ACCENT,to=(0,0,u(2),size))
            if mark=='shadow':normal.put(LINE,to=(edge,size-u(1),size-edge,size))
            images=[]
            for state,color,stroke in states:
                picture=rounded_image(self.root,size,edge,color,stroke,outer);self.images.append(picture)
                if mark=='line':picture.put(ACCENT if state=='focus' else LINE,to=(0,size-u(2 if state=='focus' else 1),size,size))
                if mark=='left':picture.put(ACCENT,to=(0,0,u(2),size))
                if mark=='shadow' and state!='pressed':picture.put(LINE,to=(edge,size-u(1),size-edge,size))
                if mark=='focusline' and state=='focus':picture.put(ACCENT,to=(0,size-u(2),size,size))
                elif mark=='bottom' and state=='selected':picture.put(ACCENT,to=(0,size-u(2),size,size))
                images.append((state,picture))
            borders=(u(2),edge,edge,edge) if mark=='left' else (edge,edge,edge,u(2)) if mark in ('bottom','line','shadow','focusline') else edge
            style.element_create(name+suffix,'image',normal,*images,border=borders,padding=0,sticky='nswe')
        def button(style_name,element_name):
            style.layout(style_name,[(element_name+suffix,{'sticky':'nswe','children':[
                ('Button.padding',{'sticky':'nswe','children':[('Button.label',{'sticky':'nswe'})]})]})])
        element('Archive.Button',CANVAS,radius=3,mark='shadow',states=(('disabled',DISABLED,None),('pressed',SELECTED,None),('focus',HOVER,ACCENT),('active',HOVER,None)))
        button('TButton','Archive.Button')
        element('Archive.Primary',ACCENT,radius=4,states=(('disabled',DISABLED,None),('pressed',self.color('#111111'),None),('focus',self.color('#404040'),PAPER),('active',self.color('#404040'),None)))
        button('Primary.TButton','Archive.Primary')
        element('Archive.Quiet',PAPER,radius=2,mark='focusline',states=(('pressed',SELECTED,None),('focus',HOVER,None),('active',HOVER,None)))
        for name in ('Quiet.TButton','Disclosure.TButton','PowerModel.TButton'):
            button(name,'Archive.Quiet')
        element('Archive.AiQuiet',self.palette['AI'],outer=self.palette['AI'],radius=2,mark='focusline',states=(('pressed',SELECTED,None),('focus',HOVER,None),('active',HOVER,None)))
        button('Copilot.TButton','Archive.AiQuiet');button('AiQuiet.TButton','Archive.AiQuiet')
        element('Archive.PowerChip',SELECTED,outer=self.palette['AI'],radius=15,states=(('pressed',HOVER,None),('focus',SELECTED,LINE),('active',HOVER,None)))
        button('PowerChip.TButton','Archive.PowerChip');style.configure('PowerChip.TButton',font=self.small,padding=(u(12),u(5)),borderwidth=0,foreground=SECONDARY)
        element('Archive.Nav',SIDEBAR,outer=SIDEBAR,radius=0,mark='focusline',states=(('pressed',SELECTED,None),('focus',HOVER,None),('active',HOVER,None)))
        element('Archive.SelectedNav',SELECTED,outer=SIDEBAR,radius=0,mark='focusline',states=(('pressed',HOVER,None),('focus',SELECTED,None),('active',HOVER,None)))
        for name,shape in (('Nav.TButton','Archive.Nav'),('SelectedNav.TButton','Archive.SelectedNav')):
            button(name,shape);style.configure(name,anchor='w',font=self.body,padding=(u(12),u(11)),background=SIDEBAR,foreground=INK)
        style.configure('SelectedNav.TButton',font=self.name)
        element('Archive.Entry',CANVAS,radius=3,mark='line',states=(('focus',CANVAS,None),('disabled',DISABLED,None)))
        style.layout('TEntry',[('Archive.Entry'+suffix,{'sticky':'nswe','children':[
            ('Entry.padding',{'sticky':'nswe','children':[('Entry.textarea',{'sticky':'nswe'})]})]})])
        style.layout('Search.TEntry',[('Archive.Entry'+suffix,{'sticky':'nswe','children':[
            ('Entry.padding',{'sticky':'nswe','children':[('Entry.textarea',{'sticky':'nswe'})]})]})])
        style.configure('Search.TEntry',padding=(u(12),u(7)),fieldbackground=CANVAS,borderwidth=0)
        from .icon_button import icon_image
        arrow_name='Archive'+suffix+'.downarrow'
        arrow=icon_image(self.root,'chevron',SECONDARY,u(15));muted_arrow=icon_image(self.root,'chevron',MUTED,u(15));self.images.extend((arrow,muted_arrow))
        style.element_create(arrow_name,'image',arrow,('disabled',muted_arrow),border=0,sticky='')
        layout=style.layout('TCombobox')
        def replace(nodes):
            return [('Archive.Entry'+suffix if name=='Combobox.field' or name.startswith('Archive.Entry') else arrow_name if name.endswith('downarrow') else name,
                     {key:replace(value) if key=='children' else value for key,value in options.items()}) for name,options in nodes]
        style.layout('TCombobox',replace(layout))
        element('Archive.AiEntry',self.palette['AI'],outer=self.palette['AI'],states=(('focus',self.palette['AI'],INK),('disabled',self.palette['AI'],None)))
        def ai_layout(nodes):
            return [('Archive.AiEntry'+suffix if name.startswith('Archive.Entry') else name,{key:ai_layout(value) if key=='children' else value for key,value in opts.items()}) for name,opts in nodes]
        style.layout('Copilot.TCombobox',ai_layout(style.layout('TCombobox')))
        style.configure('Copilot.TCombobox',padding=u(3),fieldbackground=self.palette['AI'],background=self.palette['AI'],foreground=INK,arrowsize=u(9))
        element('Archive.Tab',PAPER,outer=PAPER,radius=0,mark='bottom',states=(('selected',PAPER,None),('focus',HOVER,INK),('active',HOVER,None)))
        style.layout('TNotebook.Tab',[('Archive.Tab'+suffix,{'sticky':'nswe','children':[
            ('Notebook.padding',{'sticky':'nswe','children':[('Notebook.label',{'sticky':'nswe'})]})]})])

    def text_surface(self,widget,editable=False,framed=False,background=PAPER):
        """One readable text style, including ScrolledText's native scrollbar."""
        u=self.u;PAPER,CANVAS,INK,SELECTED,LINE=(self.palette[key] for key in ('PAPER','CANVAS','INK','SELECTED','LINE'));background=self.color(background)
        widget.configure(background=background,foreground=INK,insertbackground=INK,
                         selectbackground=SELECTED,selectforeground=INK,relief='flat',borderwidth=0,
                         highlightthickness=u(1) if framed else 0,highlightbackground=LINE,highlightcolor=INK,
                         padx=u(10),pady=u(9),spacing1=u(1),spacing3=u(4),insertwidth=u(2) if editable else u(1),insertofftime=500)
        if hasattr(widget,'vbar'):
            widget.frame.configure(background=background)
            widget.vbar.pack_forget();widget.vbar.destroy()
            from .slim_scrollbar import SlimScrollbar
            widget.vbar=SlimScrollbar(widget.frame,self,orient='vertical',command=widget.yview)
            widget.vbar.pack(side='right',fill='y');widget.configure(yscrollcommand=widget.vbar.set)
        self.wheel_router.register(widget,widget)

    def u(self,value):return max(1,round(value*self.scale))

    def update(self,text_size,family,mode,language,wheel_speed):
        requested_family=family if family in self.available_fonts else next((name for name in ('Microsoft YaHei UI','Microsoft YaHei','Segoe UI','Arial') if name in self.available_fonts),'TkDefaultFont')
        fonts_changed=(text_size,requested_family)!=(self.text_size,self.family)
        old={'body':self.body[1],'small':self.small[1],'name':self.name[1],'title':self.title[1],'section':self.section[1]}
        previous_mode=self.active_mode;self.mode=mode;self.language=language;self.active_mode=self.resolved_mode()
        palette_changed=previous_mode!=self.active_mode;self.wheel_router.pixels=self.u(wheel_speed)
        if not fonts_changed and not palette_changed:return {'fonts':False,'palette':False}
        self.palette=dict(PALETTES[self.active_mode]);self._font_details_cache={}
        if fonts_changed:self.set_fonts(text_size,family)
        previous=self.images
        if not palette_changed:self.generation+=1
        if palette_changed:self.configure_styles()
        else:self.configure_font_styles()
        self._defer_hidden=True
        try:self.apply_tree(self.root,old if fonts_changed else None)
        finally:self._defer_hidden=False
        if palette_changed:
            for picture in previous:self.root.tk.call('image','delete',str(picture))
        return {'fonts':fonts_changed,'palette':palette_changed}

    def prepare(self,widget):
        pending=getattr(widget,'_pending_theme',None)
        if not pending:return
        del widget._pending_theme;previous=getattr(self,'_defer_hidden',False);self._defer_hidden=True
        try:self.apply_tree(widget,pending['old_fonts'])
        finally:self._defer_hidden=previous

    def apply_tree(self,parent,old_fonts=None,ai=False):
        if getattr(self,'_defer_hidden',False) and getattr(parent,'_lazy_theme',False) and not parent.winfo_ismapped():
            previous=getattr(parent,'_pending_theme',{})
            parent._pending_theme={'old_fonts':previous.get('old_fonts') or old_fonts,'generation':self.generation}
            return
        pending=getattr(parent,'_pending_theme',None)
        if pending:
            old_fonts=pending['old_fonts'] or old_fonts;del parent._pending_theme
        import tkinter as tk
        from .slim_scrollbar import SlimScrollbar
        ai=bool(getattr(parent,'_ai_surface',ai))
        if getattr(parent,'_ai_composer',False):ai=False
        try:
            from .symbol_actions import symbolize
            symbolize(parent,self)
            if hasattr(parent,'refresh_icon'):parent.refresh_icon()
            kind=parent.winfo_class()
            options=getattr(self,'_widget_options',None)
            if options is None:self._widget_options=options={}
            if kind not in options:options[kind]=frozenset(parent.keys())
            keys=options[kind]
            for name in ('background','foreground','activebackground','activeforeground','insertbackground','selectbackground','selectforeground','highlightbackground','highlightcolor'):
                if name in keys:
                    current=parent.cget(name);value=self.color(current)
                    if name=='background' and ai and value in (self.palette['PAPER'],self.palette['CANVAS']):value=self.palette['AI']
                    if str(current)!=value:parent.configure(**{name:value})
            if ai and parent.winfo_class() in ('TFrame','TLabel'):
                hint='Hint' in str(parent.cget('style'))
                value='Ai.TFrame' if parent.winfo_class()=='TFrame' else 'Ai.Hint.TLabel' if hint else 'Ai.TLabel'
                if str(parent.cget('style'))!=value:parent.configure(style=value)
            self.scope_font(parent,kind)
            if old_fonts and not getattr(parent,'_auto_theme_font',False) and 'font' in keys and parent.cget('font') and parent.winfo_class() not in ('TEntry','TCombobox','TSpinbox'):
                value=str(parent.cget('font'))
                if value not in (str(self.font),str(self.small_font)):
                    self.update_widget_font(parent,old_fonts)
            if parent.winfo_class() in ('TEntry','TCombobox','TSpinbox'):
                parent.configure(font=self.small if 'Copilot' in str(parent.cget('style')) else self.body)
            if isinstance(parent,tk.Canvas):
                for item in parent.find_all():
                    for name in ('fill','outline'):
                        try:
                            value=parent.itemcget(item,name)
                            if value and value!=self.color(value):parent.itemconfigure(item,**{name:self.color(value)})
                        except tk.TclError:pass
                    if old_fonts and parent.type(item)=='text':
                        parent.itemconfigure(item,font=self.mapped_font(parent.itemcget(item,'font'),old_fonts))
            if isinstance(parent,tk.Text):
                for tag in parent.tag_names():
                    for name in ('foreground','background'):
                        value=parent.tag_cget(tag,name)
                        if value and value!=self.color(value):parent.tag_configure(tag,**{name:self.color(value)})
                    if old_fonts and parent.tag_cget(tag,'font'):
                        parent.tag_configure(tag,font=self.mapped_font(parent.tag_cget(tag,'font'),old_fonts))
            if isinstance(parent,SlimScrollbar):
                parent.surface='AI' if ai else 'PAPER';parent.draw()
            if parent.winfo_class()=='Menu':
                parent.configure(background=self.palette['PAPER'],foreground=self.palette['INK'],activebackground=self.palette['SELECTED'],activeforeground=self.palette['INK'],relief='flat',borderwidth=0,font=self.body)
        except tk.TclError:pass
        for child in parent.winfo_children():self.apply_tree(child,old_fonts,ai)

    def mapped_font(self,description,old_fonts):
        cache=getattr(self,'_font_details_cache',None)
        if cache is None:self._font_details_cache=cache={}
        key=(str(description),tuple(sorted(old_fonts.items())))
        if key not in cache:
            parts=self.root.tk.splitlist(str(description))
            try:
                size=int(parts[1]);weight='bold' if 'bold' in ' '.join(parts[2:]).split() else 'normal'
            except (IndexError,ValueError):
                try:
                    size=int(self.root.tk.call('font','configure',str(description),'-size'))
                    weight=str(self.root.tk.call('font','configure',str(description),'-weight'))
                except TclError:
                    original=font.Font(self.root,font=description);size=-round(abs(original.cget('size'))*float(self.root.tk.call('tk','scaling')));weight=original.cget('weight')
            if size==old_fonts['title'] and weight=='bold':size=self.title[1]
            elif size==old_fonts['section'] and weight=='bold':size=self.section[1]
            elif size==old_fonts['name'] and weight=='bold':size=self.name[1]
            elif size==old_fonts['body']:size=self.body[1]
            elif size==old_fonts['small']:size=self.small[1]
            cache[key]=(self.family,size,weight)
        return cache[key]

    def update_widget_font(self,widget,old_fonts):
        current=widget.cget('font');target=self.mapped_font(current,old_fonts)
        if tuple(self.root.tk.splitlist(str(current)))!=tuple(map(str,target)):widget.configure(font=target)

    def close(self):
        self.action_maps_closed=True
        self.wheel_router.close()
        for picture in self.images:
            self.root.tk.call('image','delete',str(picture))
        self.images.clear()
        if hasattr(self,'icon_cache'):self.icon_cache.clear()

    def elide(self,text,width,small=False,renderer=None):
        renderer=renderer or (self.small_font if small else self.font)
        if renderer.measure(text)<=width:return text
        room=max(0,width-renderer.measure('…'));lo=0;hi=len(text)
        while lo<hi:
            mid=(lo+hi+1)//2
            if renderer.measure(text[:mid])<=room:lo=mid
            else:hi=mid-1
        return text[:lo]+'…'
