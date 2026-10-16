"""Canonical source ranges, independent of translated captions."""
from ..errors import ValidationError

SOURCE_RANGES={'全部电脑本地记录':None,'最近 500 条':500,'最近 5000 条':5000,'最近 5 万条':50000,'最近 10 万条':100000,'最近 100 万条':1000000,'最近 50 条':50}

def selected_range(label):
    if label not in SOURCE_RANGES:raise ValidationError('请选择有效读取范围。')
    limit=SOURCE_RANGES[label]
    return limit is None,limit or 1000000
