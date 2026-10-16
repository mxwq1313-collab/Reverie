"""只读一致性快照 → UTF-8 HTML/TXT；已有目录与文件不覆盖。"""

from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
import time

from ..database.db import APPLICATION_ID, MAX_READABLE_SCHEMA_VERSION, default_data_dir
from ..errors import ConflictError, NotFoundError, ValidationError
from ..migration.manager import validate_schema


STYLE = """
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#f3f5f4;color:#20382f;font:16px/1.65 'Microsoft YaHei',sans-serif}
main{max-width:960px;margin:28px auto;padding:0 20px}header,.empty{background:white;border-radius:14px;padding:24px;margin-bottom:22px}
h1{font-size:25px;margin:0 0 10px}p{margin:8px 0}.metadata{color:#60746a;font-size:14px;overflow-wrap:anywhere}
article{margin:16px 0;max-width:85%}.side-b{margin-left:auto}.sender{font-weight:600}.stamp{font-size:13px;color:#60746a;margin:3px 0}
.body{margin:0;border-radius:12px;background:white;padding:14px 18px;white-space:pre-wrap;overflow-wrap:anywhere;color:#172b24}
.side-b .body{background:#dff1e5}.recipient{font-size:12px;color:#718279}a{color:#236552}li{margin:10px 0}
@media(max-width:600px){main{padding:0 12px;margin:12px auto}article{max-width:95%}header{padding:18px}}
@media print{body{background:white}main{max-width:none;margin:0}article{break-inside:avoid}.body{border:1px solid #ddd}}
"""


def _local_path(value):
    if not isinstance(value, (str, Path)):
        raise ValidationError('请选择明确的本机文件或保存目录')
    raw = str(value)
    path = Path(raw).expanduser()
    if not raw or '://' in raw or raw.startswith(('\\\\', '//')) or '..' in path.parts or any(ord(c) < 32 for c in raw):
        raise ValidationError('请使用明确的本机路径，不接受 URI、网络路径或 ..')
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValidationError('导出路径不接受符号链接或目录联接')
    return path.resolve()


def _display_zone(value):
    if not isinstance(value, str) or not re.fullmatch(r'[+-]\d{2}:\d{2}', value):
        raise ValidationError('显示时区应为 +08:00 或 -05:00 等固定偏移')
    hour, minute = map(int, value[1:].split(':'))
    if hour > 14 or minute > 59 or hour == 14 and minute:
        raise ValidationError('显示时区偏移超出范围')
    return timezone((1 if value[0] == '+' else -1) * timedelta(hours=hour, minutes=minute))


def _time(stamp, zone, message_id):
    try:
        value = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('missing timezone')
        return value.astimezone(zone).isoformat(sep=' ', timespec='microseconds')
    except (ValueError, TypeError, AttributeError, OverflowError) as exc:
        raise ConflictError(f'归档消息 {message_id} 的时间不合法，未生成完整导出') from exc


def _head(title):
    return ('<!doctype html>\n<html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
            f'<title>{escape(title)}</title><style>{STYLE}</style></head><body><main>\n')


def _publish_directory(staging, target):
    for attempt in range(6):
        if target.exists():
            raise ConflictError('保存位置已被创建，未覆盖；请重新选择新目录')
        try:
            staging.rename(target)
            return
        except PermissionError as error:
            # Windows 外部文件句柄可能短暂阻止目录改名；不改权限、不覆盖目标。
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 32) or attempt == 5:
                raise
            time.sleep(0.1 * (attempt + 1))


def export_readable(database, output_dir, *, user_id=None, peer_id=None, formats=('html', 'txt'), display_timezone='+08:00'):
    """导出全部或指定双向会话。来源只读；输出目录必须是新目录。"""
    for value in (user_id, abs(peer_id) if type(peer_id) is int else peer_id):
        if value is not None and (type(value) is not int or not 1 <= value <= 2**63 - 1):
            raise ValidationError('参与者 ID 必须是正整数')
    if peer_id is not None and user_id is None:
        raise ValidationError('指定对方时也需要指定查看身份 --user')
    if not isinstance(formats, (tuple, list)) or not formats or any(not isinstance(value, str) or value not in {'html', 'txt'} for value in formats) or len(set(formats)) != len(formats):
        raise ValidationError('导出格式只能为 html、txt 或两者')
    zone = _display_zone(display_timezone)
    source = _local_path(database if database is not None else default_data_dir() / 'chat.db')
    target = _local_path(output_dir)
    if not source.is_file():
        raise NotFoundError('归档数据库不存在；导出不会自动创建数据库')
    if target.exists():
        raise ConflictError('导出目录已存在，请选择新的目录；原文件不会覆盖')
    connection = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    staging = None
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        if connection.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID or not 1 <= version <= MAX_READABLE_SCHEMA_VERSION:
            raise ConflictError('只支持项目归档库，不读取微信原数据库或未知 SQLite 格式')
        validate_schema(connection, version)
        people = {row['id']: dict(row) for row in connection.execute('SELECT * FROM users')}
        for value in (user_id, abs(peer_id) if type(peer_id) is int else peer_id):
            if value is not None and value>=0 and value not in people:
                raise NotFoundError(f'归档参与者 ID {value} 不存在')
        clauses, params = [], []
        if peer_id is not None and peer_id<0:
            from .rich_readable import export_rich
            return export_rich(source,target,user_id=user_id,peer_id=peer_id,formats=formats,display_timezone=display_timezone)
        if peer_id is not None:
            clauses.append('((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))')
            params.extend((user_id, peer_id, peer_id, user_id))
        elif user_id is not None:
            clauses.append('(sender_id=? OR receiver_id=?)')
            params.extend((user_id, user_id))
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        if version==3 and connection.execute("SELECT COUNT(*) FROM messages WHERE msg_type!='text' OR chat_id IN (SELECT id FROM chats WHERE kind='group')").fetchone()[0]:
            from .rich_readable import export_rich
            return export_rich(source,target,user_id=user_id,peer_id=peer_id,formats=formats,display_timezone=display_timezone)
        if connection.execute('SELECT COUNT(*) FROM messages' + where + (' AND ' if clauses else ' WHERE ') + "msg_type != 'text'", params).fetchone()[0]:
            raise ConflictError('归档含未支持的非文本消息，本次可读导出明确拒绝')
        pairs = [dict(row) for row in connection.execute('SELECT MIN(sender_id,receiver_id) AS a, MAX(sender_id,receiver_id) AS b, COUNT(*) AS count FROM messages' + where + ' GROUP BY a,b ORDER BY a,b', params)]
        if version >= 2:
            unsupported = connection.execute("SELECT COUNT(*) FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE kind NOT IN ('private','note'))" + (' AND ' + ' AND '.join(clauses) if clauses else ''), params).fetchone()[0]
            if unsupported:
                raise ConflictError('归档含未支持的会话类型，本次只导出私聊和笔记')
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.chat-export-', dir=target.parent)).resolve()
        conversations = []
        for pair in pairs:
            a, b, count = pair['a'], pair['b'], pair['count']
            title = f"{people[a]['nickname']} ↔ {people[b]['nickname']}" if a != b else f"{people[a]['nickname']} 的笔记"
            names = [f'chat_{a}_{b}.{kind}' for kind in formats]
            with ExitStack() as stack:
                handles = {kind: stack.enter_context((staging / f'chat_{a}_{b}.{kind}').open('x', encoding='utf-8', newline='\n')) for kind in formats}
                if 'html' in handles:
                    header = f'<header><h1>{escape(title)}</h1><p>{count} 条文本 · 显示时区 UTC{escape(display_timezone)}</p><p class="metadata">'
                    header += '<br>'.join(f"用户 {person_id}：{escape(people[person_id]['nickname'])} · 标识 {escape(people[person_id]['wxid'])}" for person_id in sorted({a, b}))
                    header += '</p><p class="metadata">离线文件，可使用浏览器查找或打印保存。正文保持原文。</p></header>\n'
                    handles['html'].write(_head(title) + header)
                if 'txt' in handles:
                    handles['txt'].write(f'聊天记录：{title}\n消息总数：{count}\n显示时区：UTC{display_timezone}\n')
                    for person_id in sorted({a, b}):
                        handles['txt'].write(f"用户 {person_id}：{people[person_id]['nickname']}\n标识：{people[person_id]['wxid']}\n")
                    handles['txt'].write('\n' + '=' * 60 + '\n\n')
                rows = connection.execute('SELECT * FROM messages WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) ORDER BY create_time,id', (a, b, b, a))
                written = 0
                for row in rows:
                    if not isinstance(row['content'], str):
                        raise ConflictError(f"消息 {row['id']} 不是原始文本，导出拒绝")
                    stamp = _time(row['create_time'], zone, row['id'])
                    sender, receiver = row['sender_id'], row['receiver_id']
                    sender_name, receiver_name = people[sender]['nickname'], people[receiver]['nickname']
                    if 'txt' in handles:
                        handles['txt'].write(f"[{stamp}] {sender_name}（用户 {sender}） → {receiver_name}（用户 {receiver}）\n{row['content']}\n\n")
                    if 'html' in handles:
                        side = 'side-b' if sender == (user_id if user_id is not None else b) else 'side-a'
                        handles['html'].write(f'<article class="{side}" data-message-id="{row["id"]}" data-sender-id="{sender}" data-receiver-id="{receiver}"><div class="sender">{escape(sender_name)} · 用户 {sender}</div><div class="stamp"><time datetime="{escape(row["create_time"], quote=True)}">{escape(stamp)}</time></div><p class="body">{escape(row["content"])}</p><div class="recipient">发送给 {escape(receiver_name)} · 用户 {receiver}</div></article>\n')
                    written += 1
                if written != count:
                    raise ConflictError('会话条数不一致，未生成完整导出')
                if 'html' in handles:
                    handles['html'].write('</main></body></html>\n')
            conversations.append({'participants': sorted({a, b}), 'messages': count, 'files': names})
        total = sum(pair['count'] for pair in pairs)
        if 'html' in formats:
            index = _head('聊天记录离线归档') + f'<header><h1>聊天记录离线归档</h1><p>{len(pairs)} 个会话 · {total} 条文本 · UTC{escape(display_timezone)}</p><p class="metadata">选择会话阅读。文件不需要微信或本机服务。</p></header><ul>'
            for pair in pairs:
                a, b = pair['a'], pair['b']
                title = f"{people[a]['nickname']} ↔ {people[b]['nickname']}" if a != b else f"{people[a]['nickname']} 的笔记"
                index += f'<li><a href="chat_{a}_{b}.html">{escape(title)}</a> · {pair["count"]} 条</li>'
            index += '</ul>' if pairs else '</ul><p class="empty">所选范围暂无聊天消息。</p>'
            (staging / 'index.html').write_text(index + '</main></body></html>\n', encoding='utf-8')
        files = []
        for path in sorted(staging.iterdir()):
            digest = hashlib.sha256()
            with path.open('rb') as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                    digest.update(chunk)
            files.append({'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()})
        manifest = {'format': 'readable-chat-export', 'format_version': '1.0', 'source_database': source.name, 'database_schema': version,
                    'exported_at': datetime.now(zone).isoformat(), 'display_timezone': display_timezone, 'messages': total, 'conversations': conversations,
                    'scope': {'user_id': user_id, 'peer_id': peer_id, 'messages_already_in_archive_only': True}, 'files': files}
        (staging / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        _publish_directory(staging, target)
        staging = None
        return {'directory': str(target), 'messages': total, 'conversations': len(pairs), 'formats': list(formats),
                'index': str(target / 'index.html') if 'html' in formats else None, 'manifest': str(target / 'manifest.json'),
                'files': [str(target / file['name']) for file in files]}
    finally:
        connection.close()
        if staging is not None:
            # 此目录由本次调用独占创建；删除前确认只在预期输出父目录内。
            if staging.resolve().parent == target.parent and staging.name.startswith('.chat-export-'):
                shutil.rmtree(staging)
