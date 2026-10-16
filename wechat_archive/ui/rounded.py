"""Native Tk rounded surfaces; child text remains selectable and accessible."""
import math
import struct
import tkinter as tk
import zlib
from functools import lru_cache


@lru_cache(maxsize=1)
def corner_vectors():
    return tuple(tuple((math.cos(math.radians(start+step*90/12)),math.sin(math.radians(start+step*90/12))) for step in range(13)) for start in (-90,0,90,180))


def rounded_points(width, height, radius):
    radius=max(0,min(radius,width/2,height/2))
    if not radius:return [0,0,width,0,width,height,0,height]
    points=[]
    for (cx,cy),vectors in zip(((width-radius,radius),(width-radius,height-radius),(radius,height-radius),(radius,radius)),corner_vectors()):
        for dx,dy in vectors:points.extend((cx+radius*dx,cy+radius*dy))
    return points


def rounded_image(root, size, radius, fill, outline=None, outer=None):
    def color(value):
        return bytes((int(value[1:3],16),int(value[3:5],16),int(value[5:7],16),255)) if value else b'\0\0\0\0'
    inside=color(fill);edge=color(outline or fill);outside=color(outer);rows=[]
    for y in range(size):
        distance = radius - y - .5 if y < radius else y - (size - radius) + .5 if y >= size-radius else 0
        inset = math.ceil(radius - math.sqrt(max(0, radius*radius-distance*distance))) if distance else 0
        row=edge*(size-inset*2)
        if outline and 0 < y < size-1:
            row=edge+inside*(size-inset*2-2)+edge
        rows.append(b'\0'+outside*inset+row+outside*inset)
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,6,0,0,0))
    png+=chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b'')
    return tk.PhotoImage(master=root,data=png,format='png')


class RoundedSurface(tk.Canvas):
    def __init__(self, parent, theme, background, fill, outline=None, radius=16, padding=12):
        super().__init__(parent, background=background, highlightthickness=0, borderwidth=0)
        self.theme = theme
        self.fill = fill
        self.outline = outline or fill
        self.radius = theme.u(radius)
        self.padding = theme.u(padding)
        self.content = tk.Frame(self, background=fill)
        self.window = self.create_window(self.padding, self.padding, window=self.content, anchor='nw')
        self.bind('<Configure>', self.resize)
        self.content.bind('<Configure>', self.fit_height)

    def fit_height(self, _=None):
        height = self.content.winfo_reqheight() + self.padding*2
        if int(float(self.cget('height'))) != height:
            self.configure(height=height)

    def resize(self, event):
        if getattr(self,'last_geometry',None)==(event.width,event.height):return
        if getattr(self,'last_geometry',(None,None))[0]!=event.width:self.itemconfigure(self.window, width=max(1, event.width-self.padding*2))
        self.last_geometry=(event.width,event.height)
        w, h = event.width-1, event.height-1
        r = min(self.radius, w/2, h/2)
        points = rounded_points(w,h,r)
        if self.find_withtag('surface'):self.coords('surface',*points)
        else:self.create_polygon(points, fill=self.theme.color(self.fill), outline=self.theme.color(self.outline), tags='surface')
        self.tag_lower('surface')

    def paint(self, fill):
        self.fill = fill
        self.content.configure(background=fill)
        self.itemconfigure('surface', fill=fill, outline=fill)
