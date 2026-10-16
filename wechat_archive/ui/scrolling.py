"""Route wheel input to the nearest scroll area, including its child widgets."""
import tkinter as tk


class WheelRouter:
    def __init__(self, root, scale=1):
        self.root = root
        self.pixels = max(24, round(48 * scale))
        self.scopes = {}
        self.remainders = {}
        self.bindings = {}
        self.jobs={}
        self.tag = 'ArchiveWheel_' + str(id(self))
        self.handlers=[]
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.handlers.append((sequence,root.bind_class(self.tag,sequence,self.wheel)))
        self.closed=False

    def attach(self, widget):
        if self.closed or not widget.winfo_exists():return
        tags = widget.bindtags()
        if self.tag not in tags:
            widget.bindtags((tags[0],self.tag,*tags[1:]))
        for child in widget.winfo_children():
            self.attach(child)

    def register(self, scope, target, canvas=False):
        self.scopes[str(scope)] = (scope, target, canvas)
        self.attach(scope)
        self.attach_later(scope)
        if str(scope) not in self.bindings:self.bindings[str(scope)] = (scope,scope.bind('<Destroy>',self.destroyed,add='+'))

    def attach_later(self,scope):
        key=str(scope)
        if self.closed or not scope.winfo_exists() or key in self.jobs:return
        def attach_once():
            self.jobs.pop(key,None);self.attach(scope)
        self.jobs[key]=self.root.after_idle(attach_once)

    def destroyed(self, event):
        job=self.jobs.pop(str(event.widget),None)
        if job:self.root.after_cancel(job)
        self.scopes.pop(str(event.widget), None)
        self.remainders.pop(str(event.widget), None)
        self.bindings.pop(str(event.widget), None)

    def close(self):
        if self.closed:return
        self.closed=True
        for sequence,command in self.handlers:
            self.root.unbind_class(self.tag,sequence)
            self.root.deletecommand(command)
        for job in self.jobs.values():
            try:self.root.after_cancel(job)
            except tk.TclError:pass
        self.jobs.clear()
        for scope,destroyed in self.bindings.values():
            if scope.winfo_exists():
                script=str(scope.tk.call('bind',scope._w,'<Destroy>'));prefix='if {"['+destroyed+' '
                scope.tk.call('bind',scope._w,'<Destroy>','\n'.join(line for line in script.splitlines() if not line.startswith(prefix)))
                scope.deletecommand(destroyed)
        self.bindings.clear()
        self.scopes.clear();self.remainders.clear()

    def candidates(self, widget):
        seen = set()
        while widget is not None:
            scope = self.scopes.get(str(widget))
            if scope and str(scope[1]) not in seen:
                seen.add(str(scope[1]))
                yield scope[1], scope[2]
            widget = getattr(widget, 'master', None)

    def wheel(self, event):
        if getattr(event, 'state', 0) & 1:
            return None  # Keep native Shift+wheel horizontal scrolling.
        delta = 120 if getattr(event, 'num', None) == 4 else -120 if getattr(event, 'num', None) == 5 else getattr(event, 'delta', 0)
        if not delta:
            return None
        for target, canvas in self.candidates(event.widget):
            try:
                first, last = target.yview()
                if last - first >= .999999 or delta > 0 and first <= .000001 or delta < 0 and last >= .999999:
                    continue
                if canvas:
                    region = target.cget('scrollregion').split()
                    height = float(region[3]) - float(region[1]) if len(region) == 4 else 0
                    if height > 0:
                        target.yview_moveto(first - delta / 120 * self.pixels / height)
                else:
                    key = str(target)
                    previous = self.remainders.get(key, 0)
                    if previous * delta > 0:
                        previous = 0
                    total = previous - delta / 120 * 3
                    steps = int(total)
                    self.remainders[key] = total - steps
                    if steps:
                        target.yview_scroll(steps, 'units')
                return 'break'
            except tk.TclError:
                continue
        # Registered areas consume their wheel even at the outermost boundary.
        return 'break' if any(self.candidates(event.widget)) else None
