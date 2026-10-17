"""Canonical WeChat identifiers for read-only presentation; original archive rows stay intact."""
import re,json,hashlib
from urllib.parse import quote,unquote

def canonical_identity(value):
    if not isinstance(value,str) or not value.startswith('wechat:'):return value
    parts=value.split(':',2)
    if len(parts)!=3:return value
    user=unquote(parts[2]).strip()
    if not re.fullmatch(r'[A-Za-z0-9_@.\-]{1,256}',user):return value
    return parts[0]+':'+parts[1]+':'+quote(user,safe='')

def _quoted(name):return '"'+name.replace('"','""')+'"'

def install_identity_views(connection):
    rows=[dict(r) for r in connection.execute('SELECT id,wxid,nickname FROM main.users')]
    groups={}
    for row in rows:groups.setdefault(canonical_identity(row['wxid']),[]).append(row)
    if not any(row['wxid']!=key or len(values)>1 for key,values in groups.items() for row in values):return {}
    mapping=[];changed={}
    for identity,values in groups.items():
        if not isinstance(identity,str) or not identity.startswith('wechat:'):
            mapping.extend((r['id'],r['id'],r['wxid'],r['nickname']) for r in values);continue
        chosen=min(values,key=lambda row:(row['wxid']!=identity,row['id']))
        def meaningful(row):return row['nickname'].strip() not in (row['wxid'],unquote(row['wxid'].rsplit(':',1)[-1]).strip())
        labels=sorted(values,key=lambda row:(not meaningful(row),row['id']!=chosen['id'],row['id']))
        label=labels[0]['nickname'] if meaningful(labels[0]) else unquote(identity.rsplit(':',1)[-1])
        for row in values:
            mapping.append((row['id'],chosen['id'],identity,label))
            if row['id']!=chosen['id']:changed[row['id']]=chosen['id']
    connection.execute('PRAGMA temp_store=MEMORY')
    connection.execute('CREATE TEMP TABLE _sixu_identity(raw_id INTEGER PRIMARY KEY,canonical_id INTEGER,wxid TEXT,nickname TEXT)')
    connection.executemany('INSERT INTO _sixu_identity VALUES (?,?,?,?)',mapping)
    columns=[r[1] for r in connection.execute('PRAGMA main.table_info(users)')]
    projection=','.join(('i.'+_quoted(col) if col in ('wxid','nickname') else 'u.'+_quoted(col))+' AS '+_quoted(col) for col in columns)
    connection.execute('CREATE TEMP VIEW users AS SELECT '+projection+' FROM main.users u JOIN _sixu_identity i ON i.raw_id=u.id WHERE u.id=i.canonical_id')
    if changed:
        def translated(field):return 'CASE '+field+''.join(' WHEN '+str(old)+' THEN '+str(new) for old,new in sorted(changed.items()))+' ELSE '+field+' END'
        columns=[r[1] for r in connection.execute('PRAGMA main.table_info(messages)')]
        projection=','.join((translated('m.'+_quoted(col)) if col in ('sender_id','receiver_id') else 'm.'+_quoted(col))+' AS '+_quoted(col) for col in columns)
        ids=','.join(str(value) for value in sorted(changed))
        affected='m.sender_id IN ('+ids+') OR m.receiver_id IN ('+ids+')'
        unaffected='(m.sender_id IS NULL OR m.sender_id NOT IN ('+ids+')) AND (m.receiver_id IS NULL OR m.receiver_id NOT IN ('+ids+'))'
        connection.execute('CREATE TEMP VIEW messages AS SELECT '+projection+' FROM main.messages m WHERE '+affected+' UNION ALL SELECT m.* FROM main.messages m WHERE '+unaffected)
        if connection.execute("SELECT 1 FROM main.sqlite_master WHERE name='chat_members'").fetchone():
            columns=[r[1] for r in connection.execute('PRAGMA main.table_info(chat_members)')]
            projection=','.join((translated('cm.'+_quoted(col)) if col=='user_id' else 'cm.'+_quoted(col))+' AS '+_quoted(col) for col in columns)
            connection.execute('CREATE TEMP VIEW chat_members AS SELECT DISTINCT '+projection+' FROM main.chat_members cm')
    return changed

def alias_only_source_change(connection,namespace,row,message_id,stored_hash):
    if not namespace.startswith('wechat:'):return False
    existing=connection.execute('SELECT sender_id,receiver_id FROM messages WHERE id=?',(message_id,)).fetchone()
    if existing is None:return False
    original={k:v for k,v in row.items() if k!='attachments'};changed=False
    for index,field in enumerate(('sender_id','receiver_id')):
        old_id=existing[index];new=row.get(field)
        if old_id is None:
            if new is not None:return False
            continue
        user=connection.execute('SELECT wxid FROM users WHERE id=?',(old_id,)).fetchone()
        if not user or not user[0].startswith(namespace+':') or not isinstance(new,str):return False
        old=unquote(user[0][len(namespace)+1:])
        if old!=new:
            if canonical_identity(user[0])!=canonical_identity(namespace+':'+quote(new,safe='')):return False
            original[field]=old;changed=True
    return changed and hashlib.sha256(json.dumps(original,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==stored_hash
