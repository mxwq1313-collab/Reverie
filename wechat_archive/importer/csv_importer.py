import csv
import hashlib
import json
from urllib.parse import quote

from .base_importer import BaseImporter
from .records import LoadedDocument
from .validator import DocumentError, FORMAT, FORMAT_VERSION, csv_timestamp, csv_timezone, text

HEADER = {"time", "sender", "receiver", "content", "type"}


class CSVImporter(BaseImporter):
    format_name = "csv"

    def __init__(self, *args, namespace="default", timezone="+08:00", **kwargs):
        super().__init__(*args, **kwargs)
        self.namespace, self.timezone = namespace, timezone

    def load(self, path):
        namespace = text(self.namespace, "namespace")
        zone = csv_timezone(self.timezone)
        users, chats, messages, lines, external_by_ref = {}, {}, [], {}, {}
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                if reader.fieldnames is None:
                    raise DocumentError("CSV 文件为空；至少需要 time,sender,receiver,content,type 表头")
                names = [name.strip() for name in reader.fieldnames]
                if len(names) != len(set(names)) or set(names) != HEADER:
                    raise DocumentError("CSV 表头必须恰好包含 time,sender,receiver,content,type，且不能重复")
                reader.fieldnames = names
                for index, row in enumerate(reader, 1):
                    lines[index] = reader.line_num
                    refs = []
                    for key in ("sender", "receiver"):
                        name = row.get(key)
                        name = name.strip() if isinstance(name, str) else ""
                        if name and "\x00" not in name:
                            if name not in users:
                                users[name] = {"id": f"u{len(users)+1}", "external_id": "csv:" + quote(namespace, safe="") + ":" + quote(name, safe=""), "nickname": name}
                                external_by_ref[users[name]["id"]] = users[name]["external_id"]
                            refs.append(users[name]["id"])
                        else:
                            refs.append("")
                    pair = tuple(sorted(set(refs)))
                    if all(refs) and pair not in chats:
                        external = hashlib.sha256(json.dumps(sorted(external_by_ref[value] for value in pair), ensure_ascii=False).encode("utf-8")).hexdigest()
                        chats[pair] = {"id": f"c{len(chats)+1}", "external_id": external, "type": "private", "participant_ids": list(pair)}
                    kind = row.get("type")
                    message = {"id": f"row{index}", "sender_id": refs[0], "receiver_id": refs[1], "chat_id": chats[pair]["id"] if pair in chats else "", "timestamp": csv_timestamp(row.get("time"), zone), "content": row.get("content"), "type": kind.strip() if isinstance(kind, str) else kind}
                    if None in row:
                        message["extra_csv_columns"] = row[None]
                    messages.append(message)
        except csv.Error as exc:
            raise DocumentError(f"CSV 第{reader.line_num}行格式错误：{exc}") from exc
        payload = {"format": FORMAT, "format_version": FORMAT_VERSION, "source": {"id": "csv:" + namespace, "name": path.name}, "users": list(users.values()), "chats": list(chats.values()), "messages": messages, "media": []}
        return LoadedDocument(payload, lines)
