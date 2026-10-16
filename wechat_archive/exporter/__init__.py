"""从归档库生成离线可读文件，不读取微信原库。"""

from .readable import export_readable

__all__ = ['export_readable']
