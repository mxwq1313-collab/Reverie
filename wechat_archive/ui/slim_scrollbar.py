"""Small, flat scrollbar without native Windows arrows or a sunken trough."""
import tkinter as tk


class SlimScrollbar(tk.Canvas):
    def __init__(self,parent,theme,command,orient='vertical'):
        self.theme=theme;self.command=command;self.orient=orient;self.first=0.;self.last=1.;self.drag=None;self.surface='PAPER'
        size=theme.u(7)
        super().__init__(parent,width=size,height=size,highlightthickness=0,borderwidth=0,
                         background=theme.color('#ffffff'),takefocus=1,cursor='arrow')
        self.bind('<Configure>',lambda _:self.draw())
        self.bind('<Enter>',lambda _:self.draw(True));self.bind('<Leave>',lambda _:self.draw())
        self.bind('<Button-1>',self.press);self.bind('<B1-Motion>',self.move);self.bind('<ButtonRelease-1>',lambda _:setattr(self,'drag',None))
        self.bind('<Up>',lambda _:self.step(-1));self.bind('<Down>',lambda _:self.step(1))
        self.bind('<Left>',lambda _:self.step(-1));self.bind('<Right>',lambda _:self.step(1))
        self.bind('<Prior>',lambda _:self.step(-1,'pages'));self.bind('<Next>',lambda _:self.step(1,'pages'))
        self.bind('<Home>',lambda _:self.jump(0));self.bind('<End>',lambda _:self.jump(1))
        self.bind('<FocusIn>',lambda _:self.draw(True));self.bind('<FocusOut>',lambda _:self.draw())

    def set(self,first,last):
        first,last=float(first),float(last)
        if (first,last)==(self.first,self.last):return
        self.first=first;self.last=last;self.draw()

    def get(self):return self.first,self.last
    def length(self):return max(1,self.winfo_height() if self.orient=='vertical' else self.winfo_width())

    def bounds(self):
        length=self.length();size=max(self.theme.u(24),length*(self.last-self.first));size=min(length,size)
        offset=(length-size)*self.first/max(.000001,1-(self.last-self.first))
        return offset,offset+size

    def draw(self,hover=False):
        background=self.theme.palette[self.surface]
        if str(self.cget('background'))!=background:self.configure(background=background)
        if self.last-self.first>=.999999:
            self.itemconfigure('thumb',state='hidden');self.draw_key=None;return
        start,end=self.bounds();color=self.theme.scroll_hover if hover or self.drag is not None else self.theme.scroll_color
        width=self.winfo_width();height=self.winfo_height();pad=max(1,self.theme.u(1))
        key=(start,end,width,height,color,background,self.orient)
        if key==getattr(self,'draw_key',None):return
        self.draw_key=key
        if not getattr(self,'thumb_items',None):
            self.thumb_items=(self.create_rectangle(0,0,1,1,tags='thumb',outline=''),self.create_oval(0,0,1,1,tags='thumb',outline=''),self.create_oval(0,0,1,1,tags='thumb',outline=''))
        if self.orient=='vertical':
            radius=max(1,(width-pad*2)/2);x1=pad;x2=max(pad+1,width-pad)
            boxes=((x1,start+radius,x2,end-radius),(x1,start,x2,start+radius*2),(x1,end-radius*2,x2,end))
        else:
            radius=max(1,(height-pad*2)/2);y1=pad;y2=max(pad+1,height-pad)
            boxes=((start+radius,y1,end-radius,y2),(start,y1,start+radius*2,y2),(end-radius*2,y1,end,y2))
        for item,box in zip(self.thumb_items,boxes):self.coords(item,*box);self.itemconfigure(item,state='normal',fill=color)

    def press(self,event):
        self.focus_set();position=event.y if self.orient=='vertical' else event.x;start,end=self.bounds()
        if start<=position<=end:self.drag=(position,self.first)
        else:self.command('scroll',-1 if position<start else 1,'pages')
        self.draw(True);return 'break'

    def move(self,event):
        if self.drag is None:return 'break'
        position=event.y if self.orient=='vertical' else event.x;start,end=self.bounds()
        available=max(1,self.length()-(end-start))
        fraction=self.drag[1]+(position-self.drag[0])/available*(1-(self.last-self.first))
        self.command('moveto',max(0,min(1,fraction)));return 'break'

    def step(self,value,unit='units'):self.command('scroll',value,unit);return 'break'
    def jump(self,value):self.command('moveto',value);return 'break'
