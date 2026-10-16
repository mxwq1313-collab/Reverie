"""Read-only rich conversations; group IDs are negative chat IDs in desktop routing."""
from ..errors import ValidationError, NotFoundError


def private_scope(owner,peer=None):
    clause="m.chat_id IN (SELECT c.id FROM chats c JOIN chat_members cm ON cm.chat_id=c.id WHERE c.kind='private' AND cm.user_id=?"
    values=[owner]
    if peer is not None:
        clause+=' AND EXISTS (SELECT 1 FROM chat_members other WHERE other.chat_id=c.id AND other.user_id=?) AND (SELECT COUNT(*) FROM chat_members members WHERE members.chat_id=c.id)=?'
        values.extend((peer,1 if peer==owner else 2))
    return clause+')',tuple(values)


class RichReader:
    def __init__(self,database):self.database=database

    def contacts(self,owner,keyword=None):
        with self.database.connection() as conn:
            if not conn.execute('SELECT 1 FROM users WHERE id=?',(owner,)).fetchone():raise NotFoundError('查看身份不存在')
            # Aggregate once for the selected identity, instead of querying every card.
            chats=[dict(x) for x in conn.execute("""
                WITH owned AS (SELECT c.* FROM chats c JOIN chat_members cm ON cm.chat_id=c.id WHERE cm.user_id=?),
                counts AS (SELECT chat_id,COUNT(*) message_count,COALESCE(SUM(sender_id=?),0) own_count FROM messages WHERE chat_id IN (SELECT id FROM owned) GROUP BY chat_id),
                latest AS (SELECT c.id chat_id,(SELECT m.id FROM messages m WHERE m.chat_id=c.id ORDER BY m.create_time DESC,m.id DESC LIMIT 1) last_id FROM owned c)
                SELECT c.*,a.message_count,a.own_count,l.content last_message,l.create_time last_time,s.wxid last_sender_wxid,l.msg_type last_msg_type,l.id last_id
                FROM owned c JOIN counts a ON a.chat_id=c.id JOIN latest x ON x.chat_id=c.id JOIN messages l ON l.id=x.last_id LEFT JOIN users s ON s.id=l.sender_id""",(owner,owner))]
            members={}
            for record in conn.execute("""
                WITH owned AS (SELECT chat_id FROM chat_members WHERE user_id=?),
                counts AS (SELECT chat_id,sender_id,COUNT(*) message_count FROM messages WHERE chat_id IN (SELECT chat_id FROM owned) GROUP BY chat_id,sender_id)
                SELECT cm.chat_id,u.*,COALESCE(a.message_count,0) message_count FROM chat_members cm JOIN users u ON u.id=cm.user_id
                LEFT JOIN counts a ON a.chat_id=cm.chat_id AND a.sender_id=cm.user_id WHERE cm.chat_id IN (SELECT chat_id FROM owned) ORDER BY message_count DESC,u.id""",(owner,)):
                row=dict(record);members.setdefault(row.pop('chat_id'),[]).append(row)
        rows=[];private={}
        for chat in chats:
            participants=members.get(chat['id'],[]);count=chat['message_count'];own=chat['own_count']
            if chat['kind']=='private':
                if len(participants) not in (1,2):continue
                user=next((x for x in participants if x['id']!=owner),next((x for x in participants if x['id']==owner),None))
                if user is None:continue
                key=user['id'];last=(chat['last_time'],chat['last_id'])
                if key not in private:
                    private[key]={key:value for key,value in user.items() if key!='message_count'}
                    private[key].update(message_count=0,own_count=0,kind='private',_latest=('',0))
                row=private[key];row['message_count']+=count;row['own_count']+=own
                if last>row['_latest']:
                    row.update({key:chat[key] for key in ('last_message','last_time','last_sender_wxid','last_msg_type')});row['_latest']=last
            else:
                group_members=[{'id':x['id'],'nickname':x['nickname'],'message_count':x['message_count'],'ratio':x['message_count']/count if count else 0} for x in participants]
                rows.append({'id':-chat['id'],'wxid':chat['chat_key'],'nickname':chat['title'] or '群聊','avatar':None,'kind':'group','members':group_members,'message_count':count,'own_count':own,'own_ratio':own/count if count else 0,
                             **{key:chat[key] for key in ('last_message','last_time','last_sender_wxid','last_msg_type')}})
        for row in private.values():
            row.pop('_latest');row['own_ratio']=row['own_count']/row['message_count'] if row['message_count'] else 0;rows.append(row)
        if keyword:rows=[x for x in rows if keyword in x['nickname'] or keyword in x['wxid'] or any(keyword in m['nickname'] for m in x.get('members',[]))]
        return sorted(rows,key=lambda x:(x['last_time'] or '',x['id']),reverse=True)

    def messages(self,owner,peer=None,keyword=None,start_time=None,end_time=None,limit=100,offset=0):
        from .chat_service import _id,_page,_time
        _id(owner,'user_id');_page(limit,offset)
        with self.database.connection() as conn:
            if peer is not None and peer<0:
                if not conn.execute("SELECT 1 FROM chats c JOIN chat_members cm ON cm.chat_id=c.id WHERE c.id=? AND c.kind='group' AND cm.user_id=?",(-peer,owner)).fetchone():raise NotFoundError('当前身份不属于此群聊')
                clause='m.chat_id=?';params=[-peer]
            elif peer is not None:
                _id(peer,'peer_id');clause,values=private_scope(owner,peer);params=list(values)
            else:
                clause="m.chat_id IN (SELECT chat_id FROM chat_members WHERE user_id=?)";params=[owner]
            if keyword:clause+=' AND instr(COALESCE(m.content,\'\'),?)>0';params.append(keyword)
            if start_time:clause+=' AND m.create_time>=?';params.append(_time(start_time))
            if end_time:clause+=' AND m.create_time<?';params.append(_time(end_time))
            if start_time and end_time and _time(start_time)>=_time(end_time):raise ValidationError('开始时间必须早于结束时间')
            total=conn.execute('SELECT COUNT(*) FROM messages m WHERE '+clause,params).fetchone()[0]
            items=[dict(x) for x in conn.execute("SELECT m.*,COALESCE(s.nickname,CASE WHEN m.msg_type='system' AND m.content LIKE '[发送者未映射]%' THEN '来源身份未映射' ELSE '系统' END) sender_name,s.wxid sender_wxid,COALESCE(r.nickname,c.title,'会话') receiver_name,c.kind chat_kind,c.title chat_title FROM messages m LEFT JOIN users s ON s.id=m.sender_id LEFT JOIN users r ON r.id=m.receiver_id LEFT JOIN chats c ON c.id=m.chat_id WHERE "+clause+' ORDER BY m.create_time,m.id LIMIT ? OFFSET ?',(*params,limit,offset))]
            indexed={row['id']:row for row in items}
            for row in items:row['attachments']=[]
            identifiers=list(indexed)
            for chunk_start in range(0,len(identifiers),400):
                chunk=identifiers[chunk_start:chunk_start+400];placeholders=','.join('?' for _ in chunk)
                for record in conn.execute('SELECT mm.message_id link_message,media.* FROM message_media mm JOIN media ON media.id=mm.media_id WHERE mm.message_id IN ('+placeholders+') ORDER BY mm.message_id,mm.ordinal',chunk):
                    value=dict(record);indexed[value.pop('link_message')]['attachments'].append(value)
        return {'items':items,'total':total,'offset':offset,'has_more':offset+len(items)<total}
