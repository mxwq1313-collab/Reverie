"""Bounded display of registered merged-forward messages; raw XML remains archived."""
import html
from xml.etree import ElementTree as ET

KIND_NAMES={'1':'文字','2':'图片','3':'语音','4':'视频','5':'链接','6':'位置','8':'文件','17':'合并转发'}

def xml_root(value):
    if not isinstance(value,str) or len(value)>2*1024*1024:return None
    if '<!DOCTYPE' in value.upper() or '<!ENTITY' in value.upper():return None
    try:return ET.fromstring(value[value.find('<'):])
    except (ET.ParseError,ValueError):return None

def forwarded_document(value,limit=100):
    root=xml_root(value)
    if root is None or root.findtext('.//appmsg/type')!='19':return None
    record=root.find('.//recorditem')
    if record is None:return None
    text=record.text or '';nested=xml_root(text)
    if nested is None:nested=xml_root(html.unescape(text))
    if nested is None:return None
    data=nested.find('datalist') if nested.tag=='recordinfo' else None
    if data is None:return None
    items=data.findall('dataitem');rows=[]
    for item in items[:max(0,min(100,limit))]:
        kind=item.get('datatype') or item.findtext('datatype') or ''
        description=item.findtext('datadesc') or item.findtext('datatitle') or ''
        body=description[:2000] if kind in ('1','5','8') else '['+KIND_NAMES.get(kind,'附件')+']'+(' '+description[:300] if description else '')
        if len(description)>(2000 if kind in ('1','5','8') else 300):body+='\n[内容较长，完整文字保留在原文中]'
        from .services.forward_resources import image_specs
        media=image_specs(item) if kind=='2' else None
        rows.append({'name':(item.findtext('sourcename') or '转发记录')[:100],'time':(item.findtext('sourcetime') or '')[:80],'text':body,'kind':kind,'media':media})
    return {'items':rows,'total':len(items)}

def forwarded_records(value,limit=100):
    document=forwarded_document(value,limit)
    return document['items'] if document else []

def forwarded_text(value,limit=8):
    document=forwarded_document(value)
    if not document or not document['items']:return None
    rows=document['items'];shown=rows[:limit];lines=[f"[合并转发 · {document['total']} 条]"]
    for row in shown:lines.extend(('',row['name']+(' · '+row['time'] if row['time'] else ''),row['text']))
    if document['total']>len(shown):lines.extend(('',f"… 另有 {document['total']-len(shown)} 条，完整内容保留在原文中。"))
    return '\n'.join(lines)
