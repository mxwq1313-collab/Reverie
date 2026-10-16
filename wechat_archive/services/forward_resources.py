"""Exact, offline forward-image recovery; never interprets opaque CDN file IDs as URLs."""
import hashlib,io,os,re
from pathlib import Path
from ..errors import ConflictError,ValidationError
from ..importer.rich_importer import ready_media

HASH=re.compile(r'[0-9a-fA-F]{32}')
MAX_BYTES=16*1024*1024

def image_specs(item):
    """Project only identities. CDN credentials stay solely in the archived XML."""
    result=[]
    for digest,size,variant in (('fullmd5','datasize','original'),('thumbfullmd5','thumbsize','thumbnail')):
        key=item.findtext(digest) or ''
        if not HASH.fullmatch(key):continue
        value=item.findtext(size) or ''
        result.append({'md5':key.lower(),'size':int(value) if value.isascii() and value.isdigit() and len(value)<10 else None,'variant':variant})
    identity=item.get('dataid') or ''
    return {'data_id':identity.lower() if HASH.fullmatch(identity) else None,'images':result}

def verified_picture(data,spec):
    from PIL import Image
    if not 0<len(data)<=MAX_BYTES or hashlib.md5(data).hexdigest()!=spec['md5']:return None
    if spec.get('size') and len(data)!=spec['size']:return None
    try:
        with Image.open(io.BytesIO(data)) as source:
            ext={'PNG':'png','JPEG':'jpg','GIF':'gif','WEBP':'webp'}.get(source.format)
            if not ext or source.width*source.height>40_000_000:return None
            source.verify()
        return ext
    except (OSError,ValueError,Image.DecompressionBombError):return None

class LocalForwardImages:
    """One account only, bounded index, no database reads or key discovery."""
    def __init__(self,account):
        self.account=Path(account);self.index=None
    def candidates(self,media):
        if self.index is None:
            self.index={};count=0
            for sub in ('msg/attach','cache','business/favorite'):
                root=self.account/sub
                if root.is_symlink():continue
                for folder,dirs,files in os.walk(root,followlinks=False):
                    dirs[:]=[d for d in dirs if not (Path(folder)/d).is_symlink() and (Path(folder)/d).resolve().is_relative_to(root.resolve())]
                    for name in files:
                        count+=1
                        if count>200000:return []
                        tokens=HASH.findall(name)
                        for token in tokens:self.index.setdefault(token.lower(),[]).append(Path(folder)/name)
        keys=[x['md5'] for x in media['images']]+([media['data_id']] if media.get('data_id') else [])
        return list(dict.fromkeys(p for k in keys for p in self.index.get(k,())))
    def acquire(self,media,directory,reader=None):
        for source in self.candidates(media):
            if source.is_symlink() or not source.resolve().is_relative_to(self.account.resolve()):continue
            before=source.stat()
            if not 0<before.st_size<=MAX_BYTES:continue
            raw=source.read_bytes();variants=[raw]
            if reader is not None and not any(verified_picture(raw,spec) for spec in media['images']):
                try:variants.append(reader.decrypt_image(str(source)))
                except (OSError,ValueError,RuntimeError):pass
            for spec in media['images']:
                for data in variants:
                    ext=verified_picture(data,spec)
                    if not ext:continue
                    after=source.stat()
                    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):continue
                    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True);target=folder/(spec['md5']+'.'+ext)
                    if target.exists() and target.read_bytes()!=data:raise ValueError('转发图片副本冲突')
                    if not target.exists():target.write_bytes(data)
                    return target,spec['variant']
        return None,None

def archived_forward_image(database,media,candidates):
    """MD5, declared size, stored SHA256 and decoder must all agree."""
    sizes={s['size'] for s in media['images'] if s.get('size')};remaining=256*1024*1024
    for item in candidates:
        if item.get('kind')!='image' or item.get('availability')!='ready' or not item.get('size_bytes') or item['size_bytes']>MAX_BYTES:continue
        if sizes and item['size_bytes'] not in sizes:continue
        if item['size_bytes']>remaining:return None
        remaining-=item['size_bytes']
        try:
            source=ready_media(database,item);data=source.read_bytes()
            for spec in media['images']:
                if verified_picture(data,spec):return dict(item)
        except (OSError,ValueError,ConflictError,ValidationError):continue
    return None
