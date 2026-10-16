"""Isolated, pinned local media retrieval. Parsing never performs decryption."""
import hashlib
import importlib.metadata
import importlib.util
from pathlib import Path
import sys
from ..errors import ArchiveError

MEDIA_SHA='ef2c2943e0b9f3a707900ee7eb08b58839a1d1e1d8eddf87a7942869bc4da221'


def local_media_reader(db,directory):
    from .acquisition import TOOL_VERSION
    distribution=importlib.metadata.distribution('wechatauto-replica')
    path=Path(distribution.locate_file('wechatauto/media.py'))
    if distribution.version!=TOOL_VERSION or hashlib.sha256(path.read_bytes()).hexdigest()!=MEDIA_SHA:raise ArchiveError('未登记的媒体读取组件')
    spec=importlib.util.spec_from_file_location('wechatauto.media',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    class LocalOnly(module.MediaDownloader):
        def _persist_key(self,*args):pass
        def _load_persisted_key(self):return None
        def _img_md5(self,row):
            import re
            from .emoji_cache import media_md5
            packed=row.get('packed_info',row.get('packed_info_data'))
            values=[x.decode().lower() for x in re.findall(rb'[0-9a-fA-F]{32}',packed)] if isinstance(packed,bytes) else []
            xml=media_md5(row,'img')
            if xml:values.append(xml)
            peer=getattr(self,'_sixu_peer',None)
            for value in dict.fromkeys(values):
                if peer and self._image_files(peer,value):return value
            return next(iter(values),None)
        def download_image(self,user,local_id,save_dir=None,aes_key=None,xor_key=None,tier=None,shard=None):
            self._sixu_peer=user;self.last_status='cache_not_found'
            try:
                result=super().download_image(user,local_id,save_dir,aes_key,xor_key,tier,shard)
                self.last_status='local_extracted' if result else 'cache_not_found'
                return result
            except RuntimeError:
                self.last_status='image_key_unavailable';raise
            except (OSError,ValueError):
                self.last_status='image_decode_failed';raise
            finally:self._sixu_peer=None
        def _scan_aes_key(self,monitor=False,monitor_timeout=0):
            if getattr(self,'_sixu_key_scan_attempted',False):return None
            self._sixu_key_scan_attempted=True
            return super()._scan_aes_key(monitor=False)
        def _image_files(self,user,md5):
            import os,re
            indexes=getattr(self,'_sixu_file_indexes',None)
            if indexes is None:self._sixu_file_indexes=indexes={}
            if user not in indexes:
                root=Path(self.db.account_dir).resolve()/'msg/attach'/self._chat_md5(user);index={};count=0
                for folder,dirs,files in os.walk(root,followlinks=False):
                    dirs[:]=[x for x in dirs if not (Path(folder)/x).is_symlink() and (Path(folder)/x).resolve().is_relative_to(root)]
                    for name in files:
                        count+=1
                        if count>200000:raise ArchiveError('所选会话图片目录超过索引预算')
                        match=re.fullmatch(r'([0-9a-fA-F]{32})(_h|_t)?\.dat',name)
                        if not match:continue
                        file=Path(folder)/name
                        if file.is_symlink() or not file.resolve().is_relative_to(root):continue
                        tier={'_h':'original','_t':'thumb',None:'mid'}[match[2]]
                        index.setdefault(match[1].lower(),{})[tier]=(str(file),file.stat().st_size)
                indexes[user]=index
            return indexes[user].get(md5.lower(),{})
        def _write_decrypted(self,data,stem,save_dir):
            # Keep the decrypted container alongside its display derivative.
            if data.startswith(b'wxgf'):
                Path(self._out(save_dir,stem+'.wxgf')).write_bytes(data)
            return super()._write_decrypted(data,stem,save_dir)
        def _wxgf_to_jpg(self,data):
            import subprocess,tempfile
            import imageio_ffmpeg
            hevc=self._extract_hevc(data)
            if not hevc:return None
            with tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'input.hevc';target=Path(folder)/'preview.jpg';source.write_bytes(hevc)
                try:
                    result=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-frames:v','1','-y',str(target)],capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    return target.read_bytes() if result.returncode==0 and target.is_file() else None
                except (OSError,subprocess.TimeoutExpired):return None
        def _out(self,save_dir,name):
            root=Path(save_dir or directory).resolve()
            if not root.is_relative_to(Path(directory).resolve()):raise ArchiveError('媒体输出目录超出本次读取范围')
            root.mkdir(parents=True,exist_ok=True)
            safe=''.join(c if c not in '/\\:*?"<>|' and ord(c)>=32 else '_' for c in str(name))[:180]
            return str(root/safe)
        def download_image_original(self,*args,**kwargs):raise ArchiveError('不驱动微信界面下载原图')
    return LocalOnly(db,save_dir=str(directory))


def acquire_media(reader,peer,row,directory):
    """Exact-shard calls only. Every output stays outside the source account."""
    base=row['local_type'] & 0xffffffff
    if base in (47,11000):
        from .emoji_cache import EmojiCache
        if not hasattr(reader,'_sixu_emoji_cache'):reader._sixu_emoji_cache=EmojiCache(reader.db.account_dir)
        return reader._sixu_emoji_cache.acquire(row,directory)
    options={'save_dir':str(directory),'shard':row['shard']}
    if base==3:result=reader.download_image(peer,row['local_id'],tier='best',**options)
    elif base==34:result=reader.download_voice(peer,row['local_id'],**options)
    elif base==43:result=reader.download_video(peer,row['local_id'],**options)
    else:return None
    if result and (not Path(result).resolve().is_relative_to(Path(directory).resolve()) or Path(result).is_symlink()):raise ArchiveError('媒体组件返回了输出目录之外的路径')
    return Path(result) if result and Path(result).is_file() else None
