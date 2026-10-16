"""Read-only aggregate statistics from an existing imported archive, never raw sources."""
from collections import Counter
from datetime import date,timedelta
import time
from ..agent.tools import ReadOnlyArchive
from ..ai.context import archive_token
from ..errors import ConflictError,NotFoundError


def archive_statistics(path,owner_id=None):
    started=time.perf_counter();token=archive_token(path);database=ReadOnlyArchive(path)
    with database.connection() as connection:
        connection.execute('BEGIN')
        rich=connection.execute('PRAGMA user_version').fetchone()[0]==3
        if owner_id is not None and not connection.execute('SELECT 1 FROM users WHERE id=?',(owner_id,)).fetchone():
            raise NotFoundError('统计身份不存在')
        if owner_id is None:where='1=1';params=()
        elif rich:where='m.chat_id IN (SELECT chat_id FROM chat_members WHERE user_id=?)';params=(owner_id,)
        else:where='(m.sender_id=? OR m.receiver_id=?)';params=(owner_id,owner_id)
        base=' FROM messages m WHERE '+where
        summary=dict(connection.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN msg_type='text' THEN length(content) ELSE 0 END),0) text_characters,COALESCE(SUM(msg_type='text'),0) text_messages,MIN(create_time) first_time,MAX(create_time) last_time,COUNT(DISTINCT sender_id) speakers"+base,params).fetchone())
        daily=[dict(x) for x in connection.execute("SELECT date(create_time,'+8 hours') day,COUNT(*) count"+base+" GROUP BY day ORDER BY day",params)]
        invalid_dates=sum(x['count'] for x in daily if not x['day']);daily=[x for x in daily if x['day']]
        hours={int(x[0]):x[1] for x in connection.execute("SELECT strftime('%H',create_time,'+8 hours'),COUNT(*)"+base+" GROUP BY 1",params) if x[0] is not None}
        kinds={x[0]:x[1] for x in connection.execute('SELECT msg_type,COUNT(*)'+base+' GROUP BY msg_type',params)}
        talkers=[dict(x) for x in connection.execute("SELECT m.sender_id id,COALESCE(u.nickname,'发送者未映射') name,COUNT(*) count FROM messages m LEFT JOIN users u ON u.id=m.sender_id WHERE "+where+' GROUP BY m.sender_id ORDER BY count DESC,m.sender_id LIMIT 8',params)]
        media={'resources':0,'bytes':0,'available':0,'missing':0}
        if rich:
            media.update(dict(connection.execute("SELECT COUNT(*) resources,COALESCE(SUM(CASE WHEN a.availability='ready' THEN a.size_bytes ELSE 0 END),0) bytes,COALESCE(SUM(a.availability='ready'),0) available,COALESCE(SUM(a.availability!='ready'),0) missing FROM media a WHERE a.id IN (SELECT mm.media_id FROM message_media mm JOIN messages m ON m.id=mm.message_id WHERE "+where+')',params).fetchone()))
            conversations=connection.execute('SELECT COUNT(DISTINCT m.chat_id)'+base,params).fetchone()[0]
            groups=connection.execute("SELECT COUNT(DISTINCT m.chat_id) FROM messages m JOIN chats c ON c.id=m.chat_id WHERE c.kind='group' AND "+where,params).fetchone()[0]
        else:
            conversations=connection.execute('SELECT COUNT(*) FROM (SELECT MIN(sender_id,receiver_id),MAX(sender_id,receiver_id)'+base+' GROUP BY 1,2)',params).fetchone()[0];groups=0
    summary.update(conversations=conversations,groups=groups,active_days=len(daily),invalid_dates=invalid_dates)
    valid=sum(hours.values());night=sum(count for hour,count in hours.items() if hour>=22 or hour<6)
    streak=best=0;previous=None
    for row in daily:
        current=date.fromisoformat(row['day']);streak=streak+1 if previous is not None and current-previous==timedelta(days=1) else 1;best=max(best,streak);previous=current
    weekday=Counter()
    for row in daily:weekday[date.fromisoformat(row['day']).weekday()]+=row['count']
    peak=max(daily,key=lambda row:row['count']) if daily else None
    if archive_token(path)!=token:raise ConflictError('统计期间归档变化，请刷新统计。')
    return {'summary':summary,'daily':daily,'hours':[hours.get(x,0) for x in range(24)],'weekdays':[weekday[x] for x in range(7)],'kinds':kinds,'talkers':talkers,'media':media,
            'fun':{'night_ratio':night/valid if valid else 0,'longest_streak':best,'peak_day':peak,'mean_text_length':summary['text_characters']/summary['text_messages'] if summary['text_messages'] else 0},
            'timezone':'UTC+08:00','scope_owner':owner_id,'source_token':token,'seconds':round(time.perf_counter()-started,4)}
