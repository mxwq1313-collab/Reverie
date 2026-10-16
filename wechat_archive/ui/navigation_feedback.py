"""A small cancellable navigation rail; page content never animates or blocks input."""
import tkinter as tk


class NavigationFeedback:
    def __init__(self,app):
        self.app=app;self.root=app.root;self.target=None;self.job=None;self.closed=False
        self.rail=tk.Frame(app.nav,background=app.theme.palette['ACCENT'],width=app.theme.u(2),takefocus=0)
        app.nav.bind('<Configure>',lambda _:self.schedule(),add='+')
        app.nav.bind('<Map>',lambda _:self.schedule(),add='+')
    def select(self,target):self.target=target;self.schedule()
    def schedule(self):
        if self.closed:return
        if self.job:self.root.after_cancel(self.job)
        self.job=self.root.after_idle(self.move)
    def move(self):
        self.job=None
        if self.closed or self.target is None or not self.target.winfo_ismapped():return
        y=self.target.winfo_y()+self.app.theme.u(8);height=max(self.app.theme.u(8),self.target.winfo_height()-self.app.theme.u(16))
        self.rail.configure(background=self.app.theme.palette['ACCENT'])
        start=self.rail.winfo_y() if self.rail.winfo_ismapped() else y
        steps=1 if self.app.ui_settings['reduce_motion'] else 6
        def frame(index):
            self.job=None
            if self.closed:return
            progress=1-(1-index/steps)**3
            self.rail.place(x=0,y=round(start+(y-start)*progress),width=self.app.theme.u(2),height=height);self.rail.lift()
            if index<steps:self.job=self.root.after(16,lambda:frame(index+1))
        frame(1)
    def close(self):
        self.closed=True
        if self.job:self.root.after_cancel(self.job)
        self.job=None
