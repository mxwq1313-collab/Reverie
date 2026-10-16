"""注册式有界解码；不猜测微信加密算法，不生成聊天消息。"""

import bz2
import hashlib
import lzma
import zlib
from abc import ABC, abstractmethod
from dataclasses import dataclass


class DecodeFailure(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass
class DecodeResult:
    code: str
    profile: str | None
    reason: str
    data: bytes | None = None
    authenticated: bool | None = None

    def summary(self):
        return {"code":self.code,"profile":self.profile,"reason":self.reason,"authenticated":self.authenticated,
                "output_bytes":len(self.data) if self.data is not None else 0,
                "output_sha256":hashlib.sha256(self.data).hexdigest() if self.data is not None else None,
                "raw_output_exported":False,"message_schema_verified":False}


class PayloadDecoder(ABC):
    requires_key = False
    @abstractmethod
    def decode(self, data: bytes, *, key: bytes | None, max_output: int) -> tuple[bytes, bool | None]:
        """需要密钥的实现须返回认证通过的结果；不能记录 key。"""


class CompressionDecoder(PayloadDecoder):
    def __init__(self, kind):
        self.kind = kind

    def decode(self, data, *, key=None, max_output=1048576):
        try:
            if self.kind in {'gzip','zlib'}:
                decoder = zlib.decompressobj(31 if self.kind=='gzip' else 15)
                output = decoder.decompress(data,max_output+1)
            elif self.kind == 'bzip2':
                decoder = bz2.BZ2Decompressor()
                output = decoder.decompress(data,max_length=max_output+1)
            elif self.kind == 'xz':
                decoder = lzma.LZMADecompressor(format=lzma.FORMAT_XZ,memlimit=64*1024*1024)
                output = decoder.decompress(data,max_length=max_output+1)
            else:
                raise DecodeFailure('unsupported_encoding','未登记的压缩格式')
            if len(output)>max_output:
                raise DecodeFailure('output_limit','解压结果超过输出上限')
            if not decoder.eof:
                raise DecodeFailure('invalid_stream','压缩流截断或未完整结束')
            if decoder.unused_data:
                raise DecodeFailure('unsupported_stream_layout','尾随数据或多段压缩流不在当前投影内')
            return output,None
        except (zlib.error,OSError,EOFError,lzma.LZMAError) as exc:
            raise DecodeFailure('invalid_stream','压缩流未通过完整解码与校验') from exc


def compression_signature(data):
    if data.startswith(b'\x1f\x8b\x08'): return 'gzip'
    if data.startswith(b'\xfd7zXZ\x00'): return 'xz'
    if len(data)>=4 and data[:3]==b'BZh' and data[3] in b'123456789': return 'bzip2'
    if len(data)>=2 and data[0]&15==8 and data[0]>>4<=7 and int.from_bytes(data[:2],'big')%31==0: return 'zlib'
    return None


class DecoderRegistry:
    def __init__(self):
        self._profiles = {kind:CompressionDecoder(kind) for kind in ('gzip','zlib','bzip2','xz')}

    def register(self, profile, decoder):
        if not isinstance(profile,str) or not profile or profile in self._profiles or not isinstance(decoder,PayloadDecoder):
            raise ValueError('解码器注册需要唯一标识和 PayloadDecoder 实例')
        self._profiles[profile] = decoder

    def decode(self, data, *, profile=None, complete=True, key=None, max_output=1048576):
        if profile is not None and (not isinstance(profile,str) or not profile):
            return DecodeResult('unsupported_encoding',None,'编码投影标识无效')
        if key is not None and not isinstance(key,bytes):
            return DecodeResult('invalid_key',profile,'密钥必须是内存中的 bytes，不记录其内容')
        if not isinstance(data,bytes) or len(data)>65536 or type(max_output) is not int or not 1<=max_output<=1048576:
            return DecodeResult('input_limit',profile,'输入或输出上限无效')
        chosen = profile or compression_signature(data)
        if not chosen:
            return DecodeResult('unknown_encoding',None,'没有已验证的编码签名；加密状态和算法均未确认')
        if chosen not in self._profiles:
            return DecodeResult('unsupported_encoding',chosen,'没有登记该编码/加密投影的解码器')
        decoder = self._profiles[chosen]
        if decoder.requires_key and key is None:
            return DecodeResult('needs_key',chosen,'已登记的解码器需要适用密钥，当前没有提供')
        if not complete:
            return DecodeResult('needs_complete_sample',chosen,'采样不完整，不能认证整个编码流')
        try:
            output,authenticated = decoder.decode(data,key=key,max_output=max_output)
            if not isinstance(output,bytes) or len(output)>max_output:
                raise DecodeFailure('output_limit','解码输出类型或大小不符合约定')
            if decoder.requires_key and authenticated is not True:
                raise DecodeFailure('authentication_failed','解密结果未经过认证，拒绝返回正文')
        except DecodeFailure as exc:
            codes={'unsupported_encoding','output_limit','invalid_stream','unsupported_stream_layout','authentication_failed'}
            code=exc.code if exc.code in codes else 'decoder_failed'
            return DecodeResult(code,chosen,'解码器拒绝该输入；没有返回或记录正文/密钥')
        except Exception:
            return DecodeResult('decoder_failed',chosen,'解码器未成功执行；没有记录内部异常或密钥')
        return DecodeResult('decoded',chosen,'已解码登记的编码流；消息 Schema 仍未验证',output,authenticated)
