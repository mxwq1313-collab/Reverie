
"""Bounded avatar decoding workers. Only show() touches Tk."""
from collections import OrderedDict,deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading,time,weakref
import tkinter as tk

class AvatarService:
    def __init__(self,root):
        self.root=root;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='sixu-avatar')
        self.pending=OrderedDict();self.active={};self.cache=OrderedDict();self.lock=threading.Lock()
        self.generation=0;self.closed=False;self.job=None;self.deliveries=deque();self.photos=OrderedDict()

    def submit(self,path,canvas,size,radius,dpi):
        if self.closed or not canvas.winfo_exists():return
        if not getattr(canvas,'_avatar_cleanup_bound',False):
            # Release Tk photos on the UI thread when a filtered row is destroyed.
            canvas.bind('<Destroy>',lambda event:setattr(event.widget,'avatar_image',None),add='+')
            canvas._avatar_cleanup_bound=True
        key=(str(path),size,radius,dpi,self.generation)
        canvas._avatar_key=key;canvas._avatar_pending=True
        if key in self.active:self.active[key][1].append(weakref.ref(canvas))
        elif key in self.pending:self.pending[key].append(weakref.ref(canvas))
        else:self.pending[key]=[weakref.ref(canvas)]
        while len(self.pending)>512:
            retired,targets=self.pending.popitem(last=False)
            for ref in targets:
                target=ref()
                if target is not None and getattr(target,'_avatar_key',None)==retired:target._avatar_pending=False
        self.start()
        if self.job is None:self.job=self.root.after(15,self.poll)

    def start(self):
        # A small bounded buffer keeps both workers busy between Tk polls.
        while self.pending and len(self.active)<8:
            key,targets=self.pending.popitem(last=False)
            self.active[key]=(self.pool.submit(self.decode,key),targets)

    def decode(self,key):
        path,size,radius,dpi,generation=key
        try:
            source=Path(path);stat=source.stat()
            if stat.st_size>4*1024*1024:return None
            stamp=(path,stat.st_mtime_ns,stat.st_size,size,radius,dpi)
            with self.lock:
                image=self.cache.get(stamp)
                if image is not None:self.cache.move_to_end(stamp);return image
            # Preload Pillow modules here; bridge registration and PhotoImage stay on Tk.
            from PIL import Image,ImageOps,ImageDraw,ImageChops,ImageTk,_imagingtk
            with Image.open(source) as image:
                if image.width*image.height>4_000_000:return None
                image=ImageOps.fit(image.convert('RGBA'),(size,size),method=Image.Resampling.LANCZOS)
            mask=Image.new('L',image.size)
            ImageDraw.Draw(mask).rounded_rectangle((0,0,size-1,size-1),radius=radius,fill=255)
            image.putalpha(ImageChops.multiply(mask,image.getchannel('A')))
            with self.lock:
                if generation==self.generation:
                    self.cache[stamp]=image
                    while len(self.cache)>256 or sum(v.width*v.height*4 for v in self.cache.values())>4*1024*1024:self.cache.popitem(last=False)
            return image
        except (OSError,ValueError):return None

    def poll(self):
        self.job=None
        if self.closed:return
        started=time.perf_counter()
        for key,(future,targets) in list(self.active.items()):
            if not future.done():continue
            self.active.pop(key)
            try:picture=future.result()
            except Exception:picture=None
            if picture is not None and key[-1]==self.generation:self.deliveries.append((key,picture,iter(targets)))
            else:
                for ref in targets:
                    target=ref()
                    if target is not None and getattr(target,'_avatar_key',None)==key:
                        target._avatar_pending=False;target._avatar_failed=key
        while self.deliveries:
            key,picture,targets=self.deliveries[0]
            target=next(targets,None)
            if target is None:self.deliveries.popleft();continue
            canvas=target()
            if canvas is not None and canvas.winfo_exists() and getattr(canvas,'_avatar_key',None)==key:self.show(canvas,picture)
            if time.perf_counter()-started>.003:break
        self.start()
        if self.active or self.pending or self.deliveries:self.job=self.root.after(8,self.poll)

    def show(self,canvas,picture):
        from PIL import ImageTk
        try:
            key=id(picture)
            if key not in self.photos:
                self.photos[key]=(picture,ImageTk.PhotoImage(picture,master=self.root))
                while len(self.photos)>256:self.photos.popitem(last=False)
            else:self.photos.move_to_end(key)
            canvas.avatar_image=self.photos[key][1]
            canvas.delete('all');canvas.create_image(picture.width//2,picture.height//2,image=canvas.avatar_image)
            canvas.avatar_available=True;canvas._avatar_pending=False
        except tk.TclError:pass

    def clear(self):
        self.generation+=1
        for targets in [*self.pending.values(),*(entry[1] for entry in self.active.values())]:
            for ref in targets:
                canvas=ref()
                if canvas is not None:canvas._avatar_pending=False
        for key,_,targets in self.deliveries:
            for ref in targets:
                canvas=ref()
                if canvas is not None and getattr(canvas,'_avatar_key',None)==key:canvas._avatar_pending=False
        self.pending.clear();self.deliveries.clear();self.photos.clear()
        for future,_ in self.active.values():future.cancel()
        self.active.clear()
        with self.lock:self.cache.clear()

    def close(self):
        self.closed=True
        if self.job:self.root.after_cancel(self.job)
        self.job=None;self.clear();self.pool.shutdown(wait=False,cancel_futures=True)
