"""Account-scoped, offline WeChat avatars; archive bytes remain untouched."""
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import unquote
from uuid import uuid4

from ..errors import ValidationError

MAX_BYTES = 4 * 1024 * 1024


def checked_image(data):
    from PIL import Image, ImageOps
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValidationError('头像文件超过预算或没有图片内容。')
    with Image.open(io.BytesIO(data)) as image:
        if image.format not in ('PNG', 'JPEG', 'WEBP', 'GIF', 'BMP') or image.width * image.height > 4_000_000:
            raise ValidationError('头像格式或尺寸未受支持。')
        image.load()
        image = ImageOps.fit(image.convert('RGBA'), (128, 128), method=Image.Resampling.LANCZOS)
        result = io.BytesIO(); image.save(result, format='PNG')
        return result.getvalue()


def user_identity(value):
    """Only the registered importer namespace has an unambiguous account binding."""
    if not isinstance(value, str) or not value.startswith('wechat:'):
        return None
    parts = value.split(':', 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return unquote(parts[1]), unquote(parts[2])


def targets(reader, owner):
    with reader.connection() as conn:
        person = conn.execute('SELECT wxid FROM users WHERE id=?', (owner,)).fetchone()
        identity = user_identity(person[0]) if person else None
        if identity is None or identity[0] != identity[1]:
            raise ValidationError('请先选择从电脑微信导入的本人身份，再更新头像。')
        account = identity[0]; namespace = 'wechat:' + account; result = {}
        for row in conn.execute('SELECT wxid FROM users WHERE id IN (SELECT user_id FROM chat_members WHERE chat_id IN (SELECT chat_id FROM chat_members WHERE user_id=?))', (owner,)):
            known = user_identity(row[0])
            if known and known[0] == account: result[row[0]] = known[1]
        if reader.version >= 3:
            for row in conn.execute("SELECT c.chat_key,(SELECT ms.source_key FROM messages m JOIN message_sources ms ON ms.message_id=m.id WHERE m.chat_id=c.id AND ms.namespace=? LIMIT 1) source_key FROM chats c JOIN chat_members cm ON cm.chat_id=c.id WHERE cm.user_id=? AND c.kind='group'", (namespace, owner)):
                try:
                    parts = json.loads(row['source_key']); peer = parts[1]
                    expected = 'group:' + hashlib.sha256((namespace + '\0' + peer).encode()).hexdigest()
                    if parts[0] == account and peer.endswith('@chatroom') and expected == row['chat_key']:
                        result[row['chat_key']] = peer
                except (ValueError, TypeError, IndexError):
                    continue
        if len(result) > 1000: raise ValidationError('头像同步最多包含1000个已归档身份，请缩小归档范围。')
        return account, result


class AvatarCache:
    def __init__(self, data_dir): self.root = Path(data_dir) / 'avatars'

    def entries(self):
        try:
            path = self.root / 'index.json'
            if path.stat().st_size > 2 * 1024 * 1024: return {}
            value = json.loads(path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError): return {}

    def decorate(self, rows):
        entries = self.entries(); result = []
        for row in rows:
            digest = entries.get(row['wxid'])
            if isinstance(digest, str) and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest):
                path = self.root / (digest + '.png')
                if path.is_file(): row = {**row, 'avatar': str(path)}
            result.append(row)
        return result

    def store(self, mapping, images, job_root):
        self.root.mkdir(parents=True, exist_ok=True); entries = self.entries(); ready = {}
        for image in images:
            if image.get('username') not in set(mapping.values()): raise ValidationError('头像返回了未选择的身份。')
            path = Path(image['path']).resolve()
            if not path.is_relative_to(Path(job_root).resolve()) or not path.is_file() or path.is_symlink():
                raise ValidationError('头像工作文件越界。')
            if path.stat().st_size > MAX_BYTES: raise ValidationError('头像文件超过预算。')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != image['sha256']: raise ValidationError('头像摘要发生变化。')
            data = checked_image(data); digest = hashlib.sha256(data).hexdigest()
            target = self.root / (digest + '.png')
            if not target.exists():
                temporary = self.root / (uuid4().hex + '.tmp'); temporary.write_bytes(data); temporary.replace(target)
            ready[image['username']] = digest
        for key, native in mapping.items():
            # Missing cache rows revoke earlier images, preventing a stale identity picture.
            if native in ready: entries[key] = ready[native]
            else: entries.pop(key, None)
        temporary = self.root / (uuid4().hex + '.json'); temporary.write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8'); temporary.replace(self.root / 'index.json')
        return {'ready': sum(native in ready for native in mapping.values()), 'missing': sum(native not in ready for native in mapping.values()), 'total': len(mapping)}
