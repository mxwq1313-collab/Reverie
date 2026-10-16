"""Verified rich batches; committed batches are resumable through source-ID dedup."""
import json
from pathlib import Path
from ..errors import ConflictError,ValidationError
from .rich_importer import RichImporter,resource_path,sha_file
from .import_report import ImportReport,utc_now


class RichSnapshotImporter:
    def __init__(self,database,*,report_dir=None,strict=False):self.database=Path(database);self.report_dir=report_dir;self.strict=strict
    def manifest(self,path):
        path=Path(path);file=path/'rich_snapshot.json'
        if file.stat().st_size>8*1024*1024:raise ValidationError('快照清单超过预算')
        data=json.loads(file.read_text(encoding='utf-8'))
        if data.get('format')!='sixu-source-snapshot' or data.get('format_version')!='1.0' or not isinstance(data.get('batches'),list):raise ValidationError('未知群聊媒体快照格式')
        for name in ('records','typed_records','unresolved_senders'):
            if type(data.get(name)) is not int or data[name]<0:raise ValidationError('快照计数字段无效')
        total=0;seen=set()
        for row in data['batches']:
            name=row.get('file');batch=resource_path(path,name)
            if name in seen or batch.parent!=path.resolve() or not batch.is_file() or sha_file(batch)!=row.get('sha256'):raise ConflictError('快照批次缺失、重复或摘要不匹配')
            seen.add(name)
            if type(row.get('records')) is not int or row['records']<0:raise ValidationError('批次计数不合法')
            total+=row['records']
        if total!=data.get('typed_records') or total+data.get('unresolved_senders',0)!=data.get('records'):raise ConflictError('来源快照计数不守恒')
        raw=resource_path(path,data.get('raw_file'))
        if not raw.is_file() or sha_file(raw)!=data.get('raw_sha256'):raise ConflictError('原始来源记录摘要不匹配')
        return data
    def preview(self,path):
        data=self.manifest(path)
        return {'kind':'rich_snapshot','messages':data['records'],'typed_records':data['typed_records'],'unresolved_senders':data['unresolved_senders'],'attachments':data['attachments'],'issues':[],'batches':len(data['batches'])}
    def import_snapshot(self,path,*,cancel_event=None,progress=None):
        path=Path(path).resolve();data=self.manifest(path);report=ImportReport(source=str(path),format='sixu-source-snapshot-1.0',database=str(self.database));committed=0;processed=0
        for batch in data['batches']:
            if cancel_event and cancel_event.is_set():break
            file=resource_path(path,batch['file'])
            if sha_file(file)!=batch['sha256']:raise ConflictError('快照在读取期间变化，已提交批次保留，可从原快照重试')
            item=RichImporter(self.database,strict=self.strict).import_file(file)
            for key in ('success_count','duplicated_count','failed_count','users_created_count','users_reused_count','chats_created_count','chats_reused_count'):
                setattr(report,key,getattr(report,key)+getattr(item,key))
            report.issues.extend(item.issues);processed+=batch['records'];committed+=1
            if progress:progress(f"正在保存聊天记录：{processed} / {data['records']}；已保存 {committed} 批，可取消后续批次")
        report.messages=data['records'];report.failed_count+=data['unresolved_senders'];report.status='partial' if report.failed_count or committed<len(data['batches']) else 'success';report.finished_at=utc_now()
        report.source_metadata={'mode':'streaming-partial-commit','processed_records':processed,'source_records':data['records'],'committed_batches':committed,'quarantined_count':report.failed_count,'snapshot':str(path),'resume':'重新导入同一封存目录；已提交来源ID去重','media_missing':data.get('media_missing',0),'media_failures':data.get('media_failures',0),'media_component':data.get('media_component')}
        report.source_metadata['retained_unmapped_senders']=data.get('retained_unmapped_senders',0)
        report.source_metadata.update(media_status_counts=data.get('media_status_counts',{}),allow_cdn=data.get('allow_cdn',False))
        if self.report_dir:report.save(self.report_dir)
        return report
