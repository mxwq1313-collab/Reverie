"""Native split handles: live geometry while dragging, preferences saved on release."""
import tkinter as tk

def split_options(theme):
    return dict(orient='horizontal',sashwidth=theme.u(8),borderwidth=0,background=theme.palette['LINE'],opaqueresize=True,
                proxybackground=theme.palette['ACCENT'],proxyborderwidth=0,sashrelief='flat')

def bind_split(app,panes,save,reset):
    state={'pressed':False,'job':None};panes._split_dragging=False
    from .layout_config import configure_changed
    def hover(event):
        configure_changed(panes,cursor='sb_h_double_arrow' if state['pressed'] or panes.identify(event.x,event.y) else '')
    def commit():
        state['job']=None
        try:
            if not app.closed:save()
        finally:
            panes._split_dragging=False
        if not app.closed:app.queue_layout()
    def destroyed(event):
        if event.widget is panes and state['job']:
            panes.after_cancel(state['job']);state['job']=None;panes._split_dragging=False
    def press(event):
        state['pressed']=bool(panes.identify(event.x,event.y))
        if state['pressed']:
            panes._split_dragging=True;panes.focus_set()
    def release(event):
        if state['pressed']:
            state['pressed']=False;state['job']=panes.after_idle(commit);hover(event)
    def nudge(direction):
        try:x,y=panes.sash_coord(0);panes.sash_place(0,x+direction*app.theme.u(24),y);save()
        except tk.TclError:pass
        return 'break'
    panes.bind('<Motion>',hover,add='+');panes.bind('<Leave>',lambda _:configure_changed(panes,cursor=''),add='+');panes.bind('<Destroy>',destroyed,add='+')
    panes.bind('<ButtonPress-1>',press,add='+');panes.bind('<ButtonRelease-1>',release,add='+')
    panes.bind('<Left>',lambda _:nudge(-1));panes.bind('<Right>',lambda _:nudge(1));panes.bind('<Home>',lambda _:reset())
    panes.bind('<Double-Button-1>',lambda _:reset(),add='+')
