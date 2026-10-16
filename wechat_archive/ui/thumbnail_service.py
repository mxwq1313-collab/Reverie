"""Visible-first thumbnails with deduplicated work, bounded queues and an idle-free poller."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import queue,weakref


def thumbnail_picture(source,width,height):
    from PIL import ImageOps
    source.draft('RGB',(width,height))
    picture=None
    for index in range(min(16,getattr(source,'n_frames',1))):
        source.seek(index);picture=ImageOps.exif_transpose(source).convert('RGBA')
        if picture.getchannel('A').getbbox() is not None:break
    picture.thumbnail((width,height));return picture.copy()


class ThumbnailService:
    def __init__(self,app):
        self.app=app;self.root=app.root;self.pool=ThreadPoolExecutor(max_workers=2,thread_name_prefix='sixu-thumbnail')
        self.events=queue.Queue();self.cache=OrderedDict();self.pending=OrderedDict();self.active={};self.closed=False;self.job=None
    def submit(self,item,canvas,width,height):
        if self.closed or not canvas.winfo_exists():return
        database=self.app.controller.require_archive()
        try:
            from ..importer.rich_importer import resource_path,media_root
            path=resource_path(media_root(database),item['relative_uri']);stat=path.stat();stamp=(stat.st_ino,stat.st_size,stat.st_mtime_ns)
        except Exception:stamp=None
        key=(str(database),item['sha256'],item.get('relative_uri'),stamp,width,height)
        if key in self.cache:self.show(canvas,self.cache[key]);self.cache.move_to_end(key);return
        if key in self.active:self.active[key]['targets'].append(weakref.ref(canvas));return
        if key in self.pending:self.pending[key]['targets'].append(weakref.ref(canvas));return
        self.pending[key]={'database':database,'item':dict(item),'width':width,'height':height,'targets':[weakref.ref(canvas)]}
        while len(self.pending)>24:
            _,old=self.pending.popitem(last=False)
            for ref in old['targets']:
                target=ref()
                if target is not None:target._thumbnail_requested=False
        self.start_jobs()
        if self.job is None:self.job=self.root.after(25,self.poll)
    def start_jobs(self):
        while self.pending and len(self.active)<2:
            key,entry=self.pending.popitem(last=False)
            targets=[ref for ref in entry['targets'] if ref() is not None and ref().winfo_exists() and getattr(ref(),'_thumbnail_visible',True)]
            if not targets:
                for ref in entry['targets']:
                    if ref() is not None:ref()._thumbnail_requested=False
                continue
            entry['targets']=targets;self.active[key]=entry
            def work(key=key,entry=entry):
                try:
                    from PIL import Image,ImageOps
                    from ..importer.rich_importer import ready_media
                    path=ready_media(entry['database'],entry['item'])
                    with Image.open(path) as source:
                        if source.width*source.height>40_000_000:raise ValueError('图片超过预览像素预算')
                        picture=thumbnail_picture(source,entry['width'],entry['height'])
                    self.events.put((key,picture,None))
                except Exception:self.events.put((key,None,'已保留附件，当前编码暂不可预览'))
            self.pool.submit(work)
    def show(self,canvas,picture):
        if self.closed or not canvas.winfo_exists():return
        from PIL import ImageTk
        photo=ImageTk.PhotoImage(picture,master=canvas);canvas.configure(width=picture.width,height=picture.height);canvas.delete('all');canvas.create_image(0,0,anchor='nw',image=photo);canvas.image=photo
        callback=getattr(canvas,'on_thumbnail_ready',None)
        if callback:callback()
    def poll(self):
        self.job=None
        if self.closed:return
        for _ in range(2):
            try:key,picture,error=self.events.get_nowait()
            except queue.Empty:break
            entry=self.active.pop(key,None)
            if entry is None:continue
            if picture is not None:
                self.cache[key]=picture
                while len(self.cache)>32 or sum(value.width*value.height*4 for value in self.cache.values())>16*1024*1024:self.cache.popitem(last=False)
            for ref in entry['targets']:
                canvas=ref()
                if self.app.controller.database!=entry['database'] or canvas is None or not canvas.winfo_exists():continue
                if not getattr(canvas,'_thumbnail_visible',True):canvas._thumbnail_requested=False;continue
                if picture is not None:self.show(canvas,picture)
                else:
                    canvas.delete('all');canvas.create_text(int(canvas.cget('width'))/2,int(canvas.cget('height'))/2,text='预览未完成',fill=self.app.theme.palette['SECONDARY'],font=self.app.theme.section);canvas.symbol_hint=error
        self.start_jobs()
        if self.active or self.pending:self.job=self.root.after(35,self.poll)
    def close(self):
        self.closed=True
        if self.job:self.root.after_cancel(self.job)
        self.job=None;self.pending.clear();self.active.clear();self.pool.shutdown(wait=False,cancel_futures=True);self.cache.clear()
