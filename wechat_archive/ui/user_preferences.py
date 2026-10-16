"""Validated desktop preferences. Existing archives and credentials stay in place."""
from pathlib import Path
from uuid import uuid4
from ..errors import ValidationError
from ..exporter.readable import _local_path

THEME_MODES=('light','dark','system','sand','blue','green','violet')

DEFAULTS={'theme':'light','font_family':'','text_size':15,'language':'zh_CN','compact_nav':False,
          'wheel_speed':48,'restore_recent':True,'reduce_motion':True,'show_ai':True,'storage_root':'','export_folder':'',
          'export_format':'HTML 和 TXT'}


def normalized(settings):
    raw=settings.get('ui',{});raw=raw if isinstance(raw,dict) else {};result=dict(DEFAULTS)
    for name,value in raw.items():
        if name in result:result[name]=value
    for name,choices in (('theme',THEME_MODES),('language',('zh_CN','en_US')),('export_format',('HTML 和 TXT','仅 HTML','仅 TXT'))):
        if result[name] not in choices:result[name]=DEFAULTS[name]
    for name,lo,hi in (('text_size',12,24),('wheel_speed',24,120)):
        if type(result[name]) is not int or not lo<=result[name]<=hi:result[name]=DEFAULTS[name]
    for name in ('compact_nav','restore_recent','reduce_motion','show_ai'):
        if type(result[name]) is not bool:result[name]=DEFAULTS[name]
    for name in ('font_family','storage_root','export_folder'):
        if not isinstance(result[name],str):result[name]=DEFAULTS[name]
    layout=settings.get('copilot_layout',{})
    if isinstance(layout,dict) and type(layout.get('expanded')) is bool:result['show_ai']=layout['expanded']
    return result


def validate(values):
    result=dict(DEFAULTS);result.update(values)
    if result['theme'] not in THEME_MODES:raise ValidationError('请选择支持的界面主题。')
    if result['language'] not in ('zh_CN','en_US'):raise ValidationError('请选择简体中文或 English。')
    if type(result['text_size']) is not int or not 12<=result['text_size']<=24:raise ValidationError('字号为12–24逻辑像素。')
    if type(result['wheel_speed']) is not int or not 24<=result['wheel_speed']<=120:raise ValidationError('滚动速度为24–120逻辑像素。')
    if not isinstance(result['font_family'],str) or len(result['font_family'])>128:raise ValidationError('请选择有效字体。')
    for name in ('compact_nav','restore_recent','reduce_motion','show_ai'):
        if type(result[name]) is not bool:raise ValidationError('界面开关应为布尔值。')
    if result['export_format'] not in ('HTML 和 TXT','仅 HTML','仅 TXT'):raise ValidationError('请选择支持的导出格式。')
    for name in ('storage_root','export_folder'):
        value=result[name]
        if not isinstance(value,str):raise ValidationError('请选择本机存储目录。')
        if not value:continue
        path=Path(value).expanduser()
        if not path.is_absolute():raise ValidationError('存储目录必须使用本机绝对路径。')
        path=_local_path(path)
        if path.exists() and not path.is_dir():raise ValidationError('存储位置必须是目录。')
        path.mkdir(parents=True,exist_ok=True)
        probe=path/('.chatarchive_write_probe_'+uuid4().hex)
        try:
            with probe.open('xb') as stream:stream.write(b'write-check')
        except OSError as error:raise ValidationError('所选存储目录不可写。') from error
        finally:
            if probe.exists():probe.unlink()
        result[name]=str(path)
    return result
