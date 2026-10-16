"""来源范围、单次读取和总读取预算；始终只读。"""

import os
from dataclasses import dataclass
from pathlib import Path

from ..base import UnsupportedWeChatSource
from .reader import checked_path,file_stamp


class SamplingError(UnsupportedWeChatSource):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass
class ReadBudget:
    limit: int = 4*1024*1024
    used: int = 0

    def __post_init__(self):
        if type(self.limit) is not int or not 1<=self.limit<=16*1024*1024 or self.used!=0:
            raise ValueError('读取预算必须为 1–16 MiB 的整数，起始 used=0')


def read_region(source, path, *, offset, length, cap, budget):
    if not isinstance(budget,ReadBudget) or type(budget.used) is not int or type(budget.limit) is not int or not 0<=budget.used<=budget.limit or not 1<=budget.limit<=16*1024*1024:
        raise SamplingError('invalid_budget','读取预算状态无效')
    source,path = checked_path(source),checked_path(path)
    if source.is_dir() and path!=source and source not in path.parents or source.is_file() and path!=source:
        raise SamplingError('out_of_scope','采样文件不在指定来源范围内')
    if path.suffix.lower() in {'.db','.sqlite','.sqlite3'} or path.name.lower()=='enmicromsg.db':
        raise SamplingError('database_rejected','载荷采样不读取数据库文件')
    if not path.is_file() or any(type(v) is not int for v in (offset,length,cap)) or offset<0 or length<0 or not 1<=cap<=65536:
        raise SamplingError('invalid_range','采样范围或单文件上限无效')
    before = file_stamp(path)
    if offset+length>before[0]:
        raise SamplingError('invalid_range','声明范围超出文件大小')
    size = min(length,cap)
    if size>budget.limit-budget.used:
        raise SamplingError('read_budget_exceeded','总读取预算不足，未继续读取')
    with path.open('rb') as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_size,opened.st_mtime_ns,opened.st_ino)!=before:
            raise SamplingError('source_changed','来源在打开前后变化')
        handle.seek(offset)
        data = handle.read(size)
    budget.used += len(data)
    if len(data)!=size or file_stamp(path)!=before:
        raise SamplingError('source_changed','来源在读取期间变化或被截断')
    return data,len(data)==length
