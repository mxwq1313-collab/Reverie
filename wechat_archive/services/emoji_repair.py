"""Repair old missing emoji attachments without changing messages or source identities."""
from collections import Counter
from contextlib import contextmanager
import hashlib,json,shutil,sqlite3,tempfile
from pathlib import Path
from ..errors import ConflictError,ValidationError
from ..importer.rich_importer import media_root,resource_path,ready_media,sha_file
from ..wechat_source.emoji_cache import message_xml
from ..wechat_source.emoji_fetch import EmojiFetch


def repair_emojis(database,*,allow_cdn=False,cancel_event=None,progress=None):
    from ..ui.import_controller import inspect_archive
    database=inspect_archive(database);counts=dict(checked=0,repaired=0,ready=0,missing=0,cancelled=False);statuses=Counter();verified={}
    @contextmanager
    def connect():
        conn=sqlite3.connect(database.as_uri()+'?mode=rw',uri=True);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:yield conn
        finally:conn.close()
    with connect() as conn:
        if conn.execute('PRAGMA user_version').fetchone()[0]!=3:raise ValidationError('请先创建扩展归档副本，再补全表情。')
        total=conn.execute("SELECT COUNT(*) FROM messages WHERE instr(content,'<emoji')>0").fetchone()[0]
    fetch=EmojiFetch(cancel_event);last_id=0
    with tempfile.TemporaryDirectory(prefix='.sixu-emoji-',dir=database.parent) as tmp:
        while True:
            with connect() as conn:rows=list(conn.execute("SELECT id,content FROM messages WHERE id>? AND instr(content,'<emoji')>0 ORDER BY id LIMIT 200",(last_id,)))
            if not rows:break
            for row in rows:
                if cancel_event and cancel_event.is_set():counts['cancelled']=True;break
                last_id=row['id'];counts['checked']+=1
                if progress and counts['checked']==1:progress(f'正在检查归档表情：1 / {total}')
                with connect() as conn:old=conn.execute("SELECT a.*,mm.ordinal FROM message_media mm JOIN media a ON a.id=mm.media_id WHERE mm.message_id=? AND a.kind='image' ORDER BY mm.ordinal LIMIT 1",(last_id,)).fetchone()
                usable=False
                if old and old['availability']=='ready':
                    try:
                        if old['id'] not in verified:ready_media(database,dict(old));verified[old['id']]=True
                        usable=True
                    except (OSError,ValidationError,ConflictError):pass
                if usable:counts['ready']+=1
                else:
                    xml=message_xml(row['content']);node=xml if xml is not None and xml.tag=='emoji' else xml.find('.//emoji') if xml is not None else None
                    file=fetch.acquire([dict(node.attrib)],tmp) if allow_cdn and node is not None else None
                    if file is None:counts['missing']+=1;statuses[fetch.last_status if allow_cdn else 'cdn_disabled']+=1
                    else:
                        digest=sha_file(file);relative=digest+'/'+file.name;destination=resource_path(media_root(database),relative);destination.parent.mkdir(parents=True,exist_ok=True)
                        if destination.exists() and sha_file(destination)!=digest:raise ConflictError('已有表情文件内容冲突，未覆盖')
                        if not destination.exists():shutil.copyfile(file,destination)
                        item={'kind':'image','relative_uri':relative,'sha256':digest,'size_bytes':file.stat().st_size,'availability':'ready','variant':fetch.last_variant}
                        item['id']=hashlib.sha256(json.dumps([item,file.name],sort_keys=True).encode()).hexdigest()
                        with connect() as conn:
                            conn.execute('BEGIN IMMEDIATE')
                            current=conn.execute('SELECT content FROM messages WHERE id=?',(last_id,)).fetchone()
                            link=conn.execute('SELECT media_id FROM message_media WHERE message_id=? AND ordinal=?',(last_id,old['ordinal'] if old else 0)).fetchone()
                            if current is None or current['content']!=row['content'] or (link[0] if link else None)!=(old['id'] if old else None):raise ConflictError('补全期间记录或附件变化，请重试')
                            conn.execute('INSERT OR IGNORE INTO media(id,kind,relative_uri,sha256,size_bytes,availability,variant) VALUES (:id,:kind,:relative_uri,:sha256,:size_bytes,:availability,:variant)',item)
                            conn.execute('DELETE FROM message_media WHERE message_id=? AND ordinal=?',(last_id,old['ordinal'] if old else 0))
                            conn.execute('INSERT INTO message_media(message_id,media_id,ordinal) VALUES (?,?,?)',(last_id,item['id'],old['ordinal'] if old else 0))
                        counts['repaired']+=1
                if progress and (counts['checked']%10==0 or counts['checked']==total):progress(f"正在补全表情：{counts['checked']} / {total}；已补全 {counts['repaired']} 条")
            if counts['cancelled']:break
    return {**counts,'total':total,'status_counts':dict(statuses)}
