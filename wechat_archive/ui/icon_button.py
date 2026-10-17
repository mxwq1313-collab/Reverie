"""Small native action buttons with vector icons and accessible text/tooltips."""
import math,struct,zlib
import tkinter as tk
from tkinter import ttk


def icon_image(root,name,color,size):
    if name=='codex':
        from PIL import Image,ImageTk
        from .codex_mark import alpha_mask
        mask=Image.frombytes('L',(64,64),alpha_mask())
        mark=Image.new('RGBA',(64,64),color);mark.putalpha(mask)
        return ImageTk.PhotoImage(mark.resize((size,size),Image.Resampling.LANCZOS),master=root)
    pixels=bytearray(size*size*4);rgb=bytes.fromhex(color.lstrip('#'));scale=size/24
    def stroke(a,b,width=1.6):
        ax,ay=(x*scale for x in a);bx,by=(x*scale for x in b);r=width*scale/2
        for y in range(max(0,int(min(ay,by)-r-1)),min(size,int(max(ay,by)+r+2))):
            for x in range(max(0,int(min(ax,bx)-r-1)),min(size,int(max(ax,bx)+r+2))):
                dx=bx-ax;dy=by-ay;t=max(0,min(1,((x+.5-ax)*dx+(y+.5-ay)*dy)/(dx*dx+dy*dy or 1)))
                alpha=max(0,min(255,round((r+.5-math.hypot(x+.5-ax-t*dx,y+.5-ay-t*dy))*255)))
                i=(y*size+x)*4
                if alpha>pixels[i+3]:pixels[i:i+4]=rgb+bytes((alpha,))
    def path(points,closed=False):
        for a,b in zip(points,points[1:]+points[:1] if closed else points[1:]):stroke(a,b)
    def rect(x,y,w,h):path([(x,y),(x+w,y),(x+w,y+h),(x,y+h)],True)
    def circle(cx,cy,r):
        points=[(cx+r*math.cos(i*math.pi/16),cy+r*math.sin(i*math.pi/16)) for i in range(32)];path(points,True)
    if name=='settings':
        circle(12,12,6);circle(12,12,2)
        for i in range(8):a=i*math.pi/4;stroke((12+6*math.cos(a),12+6*math.sin(a)),(12+9*math.cos(a),12+9*math.sin(a)))
    elif name=='history':
        path([(5,8),(8,4),(14,3),(20,7),(21,14),(17,20),(10,21),(5,18)])
        path([(3,3),(3,9),(9,9)]);path([(12,7),(12,12),(16,15)])
    elif name=='copy':rect(8,8,11,12);path([(15,5),(5,5),(5,16)])
    elif name=='search':circle(10,10,6);stroke((15,15),(21,21))
    elif name=='edit':path([(5,16),(16,5),(20,9),(9,20),(5,20),(5,16)],True);stroke((14,7),(18,11))
    elif name=='new':stroke((12,4),(12,20));stroke((4,12),(20,12))
    elif name=='save':path([(12,3),(12,15),(7,10)]);stroke((12,15),(17,10));path([(4,15),(4,21),(20,21),(20,15)])
    elif name=='send':path([(12,20),(12,4),(5,11)]);stroke((12,4),(19,11))
    elif name=='stop':rect(6,6,12,12)
    elif name=='close':stroke((6,6),(18,18));stroke((6,18),(18,6))
    elif name=='panel':rect(3,4,18,16);stroke((15,4),(15,20))
    elif name=='refresh':path([(18,6),(13,3),(7,5),(3,10),(4,16),(9,21),(16,20),(20,16)]);path([(18,2),(18,8),(12,8)])
    elif name=='fast':path([(14,2),(5,14),(11,14),(10,22),(19,10),(13,10),(14,2)],True)
    elif name=='folder':path([(3,7),(3,20),(21,20),(21,7),(12,7),(10,4),(3,4),(3,7)],True)
    elif name=='delete':path([(7,7),(8,21),(17,21),(18,7)]);stroke((4,7),(21,7));path([(9,7),(9,3),(16,3),(16,7)]);stroke((11,11),(11,17));stroke((15,11),(15,17))
    elif name=='latest':path([(5,11),(12,18),(19,11)]);stroke((12,18),(12,3));stroke((5,21),(19,21))
    elif name=='contacts':
        circle(8,7,3);circle(17,8,2.5);path([(2,21),(3,16),(6,13),(10,13),(13,16),(14,21)]);path([(15,14),(18,14),(21,17),(22,21)])
    elif name=='retry':
        path([(9,4),(4,9),(9,14)]);path([(4,9),(14,9),(19,12),(20,16),(17,20),(10,20)])
    elif name=='chat':path([(3,4),(21,4),(21,17),(10,17),(5,21),(5,17),(3,17)],True);stroke((7,9),(17,9));stroke((7,13),(14,13))
    elif name=='import':path([(5,4),(19,4),(19,21),(5,21)],True);path([(2,11),(13,11),(9,7)]);stroke((13,11),(9,15))
    elif name=='tools':path([(5,20),(15,10),(20,10),(22,6),(18,7),(16,3),(13,7),(13,11),(3,21)],True)
    elif name=='help':circle(12,12,9);path([(8,8),(10,5),(14,5),(16,8),(15,10),(12,12),(12,14)]);stroke((12,17),(12,18))
    elif name=='globe':circle(12,12,9);stroke((3,12),(21,12));path([(12,3),(7,8),(7,16),(12,21),(17,16),(17,8),(12,3)]);stroke((5,7),(19,7));stroke((5,17),(19,17))
    elif name=='calendar':rect(3,5,18,16);stroke((3,10),(21,10));stroke((7,2),(7,7));stroke((17,2),(17,7));stroke((7,14),(10,14));stroke((14,14),(17,14))
    elif name=='play':path([(7,3),(20,12),(7,21)],True)
    elif name=='preview':path([(2,12),(7,6),(17,6),(22,12),(17,18),(7,18)],True);circle(12,12,3)
    elif name=='account':circle(12,7,4);path([(4,21),(5,16),(9,13),(15,13),(19,16),(20,21)])
    elif name=='connect':path([(8,2),(8,8),(16,8),(16,2)]);path([(5,8),(5,13),(9,17),(15,17),(19,13),(19,8)],True);stroke((12,17),(12,22))
    elif name=='check':path([(4,12),(9,18),(21,5)])
    elif name=='chevron':path([(5,9),(12,16),(19,9)])
    elif name=='reset':
        path([(6,6),(12,3),(18,6),(21,12),(18,18),(12,21),(6,18)]);path([(3,3),(3,9),(9,9)])
    elif name=='capsule':
        path([(5,3),(19,3),(18,7),(13,12),(18,17),(19,21),(5,21),(6,17),(11,12),(6,7),(5,3)],True)
        stroke((9,6),(15,6));stroke((9,18),(15,18))
    elif name=='shuffle':
        path([(3,5),(7,5),(17,19),(21,19)]);path([(17,15),(21,19),(17,23)])
        path([(3,19),(7,19),(17,5),(21,5)]);path([(17,1),(21,5),(17,9)])
    elif name=='stats':
        path([(3,3),(3,21),(22,21)]);rect(6,13,3,5);rect(12,8,3,10);rect(18,3,3,15)
    elif name=='file':path([(5,2),(15,2),(20,7),(20,22),(5,22)],True);path([(15,2),(15,7),(20,7)])
    elif name=='back':path([(11,4),(3,12),(11,20)]);stroke((3,12),(21,12))
    elif name in ('more','list'):
        for y in (6,12,18):stroke((4,y),(20,y))
    else:circle(12,12,8)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+pixels[y*size*4:(y+1)*size*4] for y in range(size))
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
    return tk.PhotoImage(master=root,data=png,format='png')


class IconButton(ttk.Button):
    def __init__(self,parent,theme,icon,text,command,style='TButton'):
        self.theme=theme;self.icon=icon;self.toggled=False;self.tooltip_job=None;self.tip=None;self.icon_key=None
        super().__init__(parent,text=text,command=command,compound='image',style=style,width=0,cursor='hand2',padding=(theme.u(6),theme.u(5)))
        self.refresh_icon()
        from .symbol_actions import HoverHint
        self._action_hint=HoverHint(self,theme)

    def refresh_icon(self):
        if not self.winfo_exists():return
        from .layout_config import configure_changed
        configure_changed(self,padding=(self.theme.u(6),max(1,round((self.theme.control_height-self.theme.u(20))/2))))
        custom=getattr(self,'toggled_color',None)
        color=self.theme.palette['MUTED'] if self.instate(['disabled']) else ((custom() if callable(custom) else custom) or self.theme.palette['ACCENT']) if self.toggled else self.theme.palette['INK']
        size=self.theme.u(20);key=(self.icon,color,size)
        if key==self.icon_key:return
        self.icon_key=key
        cache=getattr(self.theme,'icon_cache',None)
        if cache is None:self.theme.icon_cache=cache={}
        if key not in cache:cache[key]=icon_image(self.theme.root,*key)
        super().configure(image=cache[key])

    def configure(self,cnf=None,**kwargs):
        result=super().configure(cnf,**kwargs)
        if 'state' in kwargs:self.refresh_icon()
        return result
    config=configure

    def state(self,statespec=None):
        value=super().state(statespec)
        if statespec is not None:self.refresh_icon()
        return value

    def schedule_tip(self,event=None):self._action_hint.schedule(event)
    def show_tip(self):
        self._action_hint.show();self.tip=self._action_hint.tip
    def hide_tip(self,event=None):
        self._action_hint.hide(event);self.tip=None
