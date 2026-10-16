"""Keep the mapped workspace stable during live resize; commit geometry once idle."""
from tkinter import ttk

class ResizeViewport(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent,style='Canvas.TFrame')
        self.pane=None;self.pinned=False;self.pin_count=0;self.release_count=0

    def attach(self,pane):
        self.pane=pane;pane.place(x=0,y=0,relwidth=1,relheight=1)

    def pin(self):
        if self.pinned or self.pane is None:return
        width,height=self.pane.winfo_width(),self.pane.winfo_height()
        if width<2 or height<2:return
        self.pinned=True;self.pin_count+=1
        self.pane.place_configure(relwidth=0,relheight=0,width=width,height=height)

    def release(self):
        if not self.pinned:return
        self.pinned=False;self.release_count+=1
        self.pane.place_configure(relwidth=1,relheight=1,width=0,height=0)
