"""Read cached emoji by the exact MD5 declared by a message; never fetch URLs."""
import hashlib
import os
from pathlib import Path
import re
import shutil
from xml.etree import ElementTree
from ..errors import ArchiveError


def message_xml(value):
    if isinstance(value,bytes):
        if value.startswith(b'\x28\xb5\x2f\xfd'):
            import io,zstandard
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(value)) as stream:
                value=stream.read(2*1024*1024+1)
        value=value.decode('utf-8',errors='replace')
    if not isinstance(value,str) or len(value)>2*1024*1024:return None
    start=value.find('<msg')
    if start<0:start=value.find('<emoji')
    if start<0:return None
    try:return ElementTree.fromstring(value[start:])
    except ElementTree.ParseError:return None


def media_md5(row,tag):
    xml=message_xml(row.get('message_content',row.get('content')))
    if xml is None:return None
    node=xml if xml.tag==tag else xml.find('.//'+tag)
    if node is None:return None
    value=node.get('md5') or node.get('androidmd5') or ''
    return value.lower() if re.fullmatch('[0-9a-fA-F]{32}',value) else None


class EmojiCache:
    def __init__(self,account_dir,*,allow_cdn=False,db=None):
        account=Path(account_dir).resolve()
        self.roots=[account/p for p in ('emoticon','emoji','msg/emoji','cache/emoji','cache/emoticon')]
        # The shared cache is distinct from other account folders.
        self.roots.extend(account.parent/p for p in ('all_users/emoji','all_users/cache/emoji','all_users/emoticon'))
        self.index=None;self.db=db;self.allow_cdn=allow_cdn;self.fetcher=None;self.last_status='cache_not_found';self.last_variant='original';self.resolved={};self.metadata={}
        self.roots.extend(p/'Emoticon' for p in (account/'cache').glob('????-??') if p.is_dir())

    def _index(self):
        self.index={};count=0
        for root in self.roots:
            if not root.is_dir() or root.is_symlink() or root.resolve()!=root:continue
            for folder,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=[x for x in dirs if not (Path(folder)/x).is_symlink() and (Path(folder)/x).resolve().is_relative_to(root)]
                for name in files:
                    count+=1
                    if count>200000:raise ArchiveError('表情缓存超过扫描预算，请缩小读取范围')
                    match=re.fullmatch(r'([0-9a-fA-F]{32})(?:\.[a-zA-Z0-9]+)?',name)
                    if match:self.index.setdefault(match[1].lower(),[]).append((root,Path(folder)/name))

    def acquire(self,row,directory):
        key=media_md5(row,'emoji')
        if not key:self.last_status='emoji_identifier_missing';return None
        if key in self.resolved:
            file,status,variant,stamp=self.resolved[key]
            current=file.stat() if file.is_file() else None
            if current and (current.st_ino,current.st_size,current.st_mtime_ns)==stamp:self.last_status=status;self.last_variant=variant;return file
            del self.resolved[key]
        if self.index is None:self._index()
        from PIL import Image
        for root,source in self.index.get(key,[]):
            if source.is_symlink() or not source.resolve().is_relative_to(root):continue
            before=source.stat()
            if not 0<before.st_size<=64*1024*1024:continue
            data=source.read_bytes()
            if hashlib.md5(data).hexdigest()!=key:continue
            try:
                with Image.open(source) as image:
                    extension={'GIF':'gif','PNG':'png','JPEG':'jpg','WEBP':'webp'}.get(image.format)
                    image.verify()
                if not extension:continue
            except (OSError,ValueError):continue
            target=Path(directory);target.mkdir(parents=True,exist_ok=True);output=target/(key+'.'+extension)
            shutil.copyfile(source,output)
            after=source.stat()
            if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or hashlib.md5(output.read_bytes()).hexdigest()!=key:
                raise ArchiveError('表情缓存在复制期间变化，请重新读取')
            self.last_status='local_verified';self.last_variant='original'
            self.remember(key,output)
            return output
        if self.allow_cdn:
            from .emoji_fetch import EmojiFetch
            if self.fetcher is None:self.fetcher=EmojiFetch()
            xml=message_xml(row.get('message_content',row.get('content')));node=xml if xml is not None and xml.tag=='emoji' else xml.find('.//emoji') if xml is not None else None
            records=[dict(node.attrib)] if node is not None else []
            if key in self.metadata:records.extend(self.metadata[key])
            elif self.db is not None:
                extra_records=[]
                for rel,_,_ in self.db._db_files:
                    if 'emoticon' not in rel.lower():continue
                    conn=self.db._open(rel)
                    try:
                        columns={x[1] for x in conn.execute('PRAGMA table_info(kNonStoreEmoticonTable)')}
                        if {'md5','cdn_url','extern_url','extern_md5','thumb_url'}<=columns:
                            extra=conn.execute('SELECT md5,cdn_url,extern_url,extern_md5,thumb_url FROM kNonStoreEmoticonTable WHERE md5=?',(key,)).fetchone()
                            if extra:extra_records.append(dict(zip(('md5','cdnurl','externurl','externmd5','thumburl'),extra)))
                    finally:conn.close()
                self.metadata[key]=extra_records;records.extend(extra_records)
                while len(self.metadata)>4096:self.metadata.pop(next(iter(self.metadata)))
            file=self.fetcher.acquire(records,directory);self.last_status=self.fetcher.last_status;self.last_variant=self.fetcher.last_variant
            if file:self.remember(key,file)
            return file
        self.last_status='local_cache_unavailable'
        return None

    def remember(self,key,file):
        stamp=file.stat();self.resolved[key]=(file,self.last_status,self.last_variant,(stamp.st_ino,stamp.st_size,stamp.st_mtime_ns))
        while len(self.resolved)>4096:self.resolved.pop(next(iter(self.resolved)))
