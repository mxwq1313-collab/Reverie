"""解密与结构解析分开。当前没有验证过的 RMFH 正文解码器。"""

from abc import ABC, abstractmethod


class BackupDecryptor(ABC):
    @abstractmethod
    def decrypt(self, encrypted: bytes, *, key: bytes, envelope: dict) -> bytes:
        """未来实现必须认证解密结果；不得把密钥写入日志。"""


class UnavailableBackupDecryptor(BackupDecryptor):
    def decrypt(self, encrypted, *, key, envelope):
        raise NotImplementedError("RMFH 密钥来源、认证解密及正文 Schema 尚未实现和验证")
