"""Fetch only an already-declared WeChat CDN emoji, with a verified digest."""
import hashlib,io,time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler,ProxyHandler
from urllib.error import HTTPError,URLError

CDN_HOSTS={'emoji.qpic.cn','mmbiz.qpic.cn','mmbiz.qlogo.cn','wx.qlogo.cn','vweixinf.tc.qq.com','wxapp.tc.qq.com'}
MAX_BYTES=16*1024*1024


def checked_url(value):
    if not isinstance(value,str) or not 1<=len(value)<=8192 or any(ord(c)<32 for c in value):raise ValueError('cdn_url_invalid')
    parts=urlsplit(value)
    if parts.scheme not in ('https','http') or parts.hostname not in CDN_HOSTS or parts.username or parts.password or parts.port not in (None,80,443):raise ValueError('cdn_host_not_allowed')
    return urlunsplit((parts.scheme,parts.hostname,parts.path,parts.query,''))


class CdnRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return super().redirect_request(req,fp,code,msg,headers,checked_url(newurl))


class EmojiFetch:
    def __init__(self,cancel_event=None):
        self.cancel_event=cancel_event
        self.opener=build_opener(ProxyHandler({}),CdnRedirects());self.cached={};self.failed=OrderedDict();self.attempts=0;self.started=time.monotonic();self.last_status='cache_not_found';self.last_variant='original'

    def acquire(self,records,directory):
        from PIL import Image
        self.last_status='cdn_url_missing';deadline=time.monotonic()+30
        for record in records:
            keys={v.lower() for k in ('md5','androidmd5','externmd5') if isinstance((v:=record.get(k)),str) and len(v)==32 and all(c in '0123456789abcdefABCDEF' for c in v)}
            if not keys:continue
            for attr in ('cdnurl','externurl','thumburl'):
                if self.cancel_event and self.cancel_event.is_set():self.last_status='cdn_cancelled';return None
                value=record.get(attr)
                if not value:continue
                try:url=checked_url(value)
                except ValueError:self.last_status='cdn_host_not_allowed';continue
                cache_key=hashlib.sha256(url.encode()).hexdigest()
                failure_key=(cache_key,tuple(sorted(keys)))
                if failure_key in self.failed:self.last_status=self.failed[failure_key];continue
                cached=self.cached.get(cache_key)
                if cached is None:
                    if time.monotonic()>deadline:self.last_status='cdn_resource_timeout';return None
                    self.attempts+=1
                    try:
                        with self.opener.open(Request(url,headers={'User-Agent':'Sixu/2.0','Accept':'image/*'}),timeout=8) as response:
                            if response.headers.get('Content-Length') and int(response.headers['Content-Length'])>MAX_BYTES:raise ValueError('cdn_too_large')
                            chunks=[];size=0
                            while True:
                                if self.cancel_event and self.cancel_event.is_set():self.last_status='cdn_cancelled';return None
                                if time.monotonic()>deadline:raise TimeoutError('resource deadline')
                                chunk=response.read(min(128*1024,MAX_BYTES+1-size))
                                if not chunk:break
                                size+=len(chunk)
                                if size>MAX_BYTES:raise ValueError('cdn_too_large')
                                chunks.append(chunk)
                            data=b''.join(chunks)
                        digest=hashlib.md5(data).hexdigest()
                        if digest not in keys:raise ValueError('cdn_digest_mismatch')
                        with Image.open(io.BytesIO(data)) as image:
                            extension={'GIF':'gif','PNG':'png','JPEG':'jpg','WEBP':'webp'}.get(image.format)
                            if not extension or image.width*image.height>40_000_000:raise ValueError('cdn_format_unsupported')
                            image.verify()
                        cached=(data,digest,extension)
                        while self.cached and sum(len(x[0]) for x in self.cached.values())+len(data)>64*1024*1024:self.cached.pop(next(iter(self.cached)))
                        self.cached[cache_key]=cached
                    except HTTPError:self.last_status='cdn_http_error'
                    except (URLError,OSError,TimeoutError):self.last_status='cdn_connection_failed'
                    except (ValueError,Image.DecompressionBombError) as error:self.last_status=str(error) if str(error).startswith('cdn_') else 'cdn_format_unsupported'
                    if cached is None:
                        self.failed[failure_key]=self.last_status
                        while len(self.failed)>2048:self.failed.popitem(last=False)
                        continue
                data,digest,extension=cached
                if digest not in keys:self.last_status='cdn_digest_mismatch';continue
                target=Path(directory);target.mkdir(parents=True,exist_ok=True);file=target/(digest+'.'+extension);file.write_bytes(data)
                self.last_status='cdn_verified';self.last_variant='original' if digest==record.get('md5','').lower() else 'compressed'
                return file
        return None
