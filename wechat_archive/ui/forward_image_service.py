"""Archive-bound asynchronous image binding for forward subrecords."""
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import queue,weakref

class ForwardImageService:
    def __init__(self,app):
        self.app=app;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='sixu-forward-image');self.events=queue.Queue();self.pending=OrderedDict();self.active=None;self.job=None;self.closed=False;self.cache={}
    def submit(self,control,index,media):
        database=self.app.controller.require_archive();token=self.app.controller.archive_view_token()
        key=(str(database),token,tuple((x['md5'],x.get('size')) for x in media['images']))
        target=(weakref.ref(control),index)
        if key in self.cache:control.media_ready(index,self.cache[key]);return
        if self.active is not None and self.active[0]==key:self.active[1].append(target);return
        if key in self.pending:self.pending[key][0].append(target);return
        media={**media,'candidates':control.row.get('attachments',[])}
        self.pending[key]=([target],media,database)
        if len(self.pending)>100:
            _,(old,_,_)=self.pending.popitem(last=False)
            for ref,position in old:
                target=ref()
                if target is not None and target.winfo_exists():target.media_ready(position,None)
        self.start()
    def start(self):
        if self.closed or self.active is not None or not self.pending:return
        key,(targets,media,database)=self.pending.popitem(last=False);self.active=(key,targets)
        reader=self.app.controller.read_snapshot(None)
        def work():
            try:
                from ..services.forward_resources import archived_forward_image
                sizes=sorted({s['size'] for s in media['images'] if s.get('size')})
                sql="SELECT * FROM media WHERE kind='image' AND availability='ready'"
                if sizes:sql+=' AND size_bytes IN ('+','.join('?' for _ in sizes)+')'
                with reader.readonly().connection() as conn:items=[dict(x) for x in conn.execute(sql+' LIMIT 100000',sizes)]
                item=archived_forward_image(database,media,[*media.get('candidates',[]),*items])
            except Exception:item=None
            self.events.put((key,item))
        self.pool.submit(work)
        if not self.job:self.job=self.app.root.after(25,self.poll)
    def poll(self):
        self.job=None
        if self.closed:return
        try:key,item=self.events.get_nowait()
        except queue.Empty:self.job=self.app.root.after(35,self.poll);return
        active=self.active;self.active=None
        if active and active[0]==key:
            if str(self.app.controller.database)==key[0] and self.app.controller.archive_view_token()==key[1]:
                self.cache[key]=item
                while len(self.cache)>100:self.cache.pop(next(iter(self.cache)))
                for ref,index in active[1]:
                    control=ref()
                    if control is not None and control.winfo_exists() and control.expanded:control.media_ready(index,item)
        self.start()
    def close(self):
        self.closed=True
        if self.job:self.app.root.after_cancel(self.job)
        self.pending.clear();self.cache.clear();self.pool.shutdown(wait=False,cancel_futures=True)
