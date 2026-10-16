"""Registered head_image table projection. No URL fetching or format guessing."""
import hashlib
from pathlib import Path
from ..errors import ArchiveError, ValidationError
from ..services.avatar_cache import checked_image


def read_avatars(db, peers, directory):
    if not isinstance(peers, list) or len(peers) > 1000 or any(not isinstance(x, str) or not x or len(x) > 256 for x in peers):
        raise ValidationError('头像同步范围无效。')
    files = [(rel, path) for rel, path, _ in db._db_files if Path(path).name == 'head_image.db']
    if len(files) != 1: raise ArchiveError('未找到唯一的微信头像缓存库，请先在微信查看联系人头像。')
    output = Path(directory); output.mkdir(parents=True, exist_ok=True); images = []; missing = 0
    conn = db._open(files[0][0])
    try:
        columns = {r['name'] for r in conn.execute('PRAGMA table_info(head_image)')}
        if not {'username', 'md5', 'image_buffer', 'update_time'} <= columns:
            raise ArchiveError('微信头像缓存结构未登记，未猜测读取。')
        for peer in dict.fromkeys(peers):
            row = conn.execute('SELECT image_buffer FROM head_image WHERE username=? ORDER BY update_time DESC LIMIT 1', (peer,)).fetchone()
            try: data = checked_image(row[0]) if row else None
            except (ValueError, OSError, ValidationError): data = None
            if data is None: missing += 1; continue
            digest = hashlib.sha256(data).hexdigest(); path = output / (digest + '.png')
            if not path.exists(): path.write_bytes(data)
            images.append({'username': peer, 'path': str(path), 'sha256': digest})
    finally: conn.close()
    if hasattr(db, 'check_read_views'): db.check_read_views()
    return {'owner': db.wxid, 'images': images, 'missing': missing, 'offline': True}
