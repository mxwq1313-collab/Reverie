import sqlite3
from dataclasses import asdict, dataclass, field

from ...importer.records import LoadedDocument
from ...importer.validator import DocumentError, validate_document
from ..base import WeChatBackupParser
from .database_reader import SQLiteDatabaseReader
from .detector import detect_android_source, load_metadata
from .errors import AndroidSourceError
from .extractor import AndroidExtractor
from .mapper import map_text_message, map_users
from .schema import load_profile, validate_schema


@dataclass(slots=True)
class AndroidParseReport:
    source: str
    status: str = "failed"
    database: str | None = None
    schema_profile: str | None = None
    contacts: int = 0
    participants: int = 0
    messages_total: int = 0
    text_messages: int = 0
    failed: int = 0
    skipped_unsupported_count: int = 0
    skipped_by_type: dict = field(default_factory=dict)
    sha256: str | None = None
    schema_signature: str | None = None
    schema_report: dict | None = None
    simulation: bool = False
    issues: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass(slots=True)
class AndroidParseResult:
    report: AndroidParseReport
    document: LoadedDocument | None = None


class AndroidWeChatParser(WeChatBackupParser):
    def __init__(self, path):
        from pathlib import Path
        # 保留原始路径到检测阶段，不能先 resolve 掩盖路径穿越。
        self.path = Path(path).expanduser()

    @staticmethod
    def detect(path):
        return detect_android_source(path).status == "candidate"

    def extract_users(self):
        if not hasattr(self, "_users"):
            result = self.parse()
            if result.document is None:
                raise AndroidSourceError("parse_failed", result.report.issues[0]["message"])
        return self._users

    def extract_messages(self):
        if not hasattr(self, "_messages"):
            result = self.parse()
            if result.document is None:
                raise AndroidSourceError("parse_failed", result.report.issues[0]["message"])
        return self._messages

    def parse(self):
        for cached in ("_users", "_messages"):
            if hasattr(self, cached):
                delattr(self, cached)
        report = AndroidParseReport(str(self.path))
        detected = detect_android_source(self.path)
        report.database = detected.database
        try:
            if detected.status != "candidate":
                raise AndroidSourceError("detection_failed", detected.reason)
            metadata = load_metadata(detected.metadata_file, detected.database)
            report.schema_profile = metadata["schema_profile"]
            report.simulation = metadata.get("simulation", False)
            profile = load_profile(metadata["schema_profile"])
            with SQLiteDatabaseReader(detected.database) as reader:
                report.sha256 = reader.sha256
                if metadata.get("database_sha256") and metadata["database_sha256"].lower() != report.sha256:
                    raise AndroidSourceError("source_hash_mismatch", "来源数据库 SHA-256 与元信息不匹配")
                report.schema_report = reader.schema_report()
                projected, report.schema_signature = validate_schema(profile, report.schema_report, metadata)
                extractor = AndroidExtractor(reader, profile, projected)
                users, namespace = map_users(extractor.contacts(), metadata["account"], profile)
                report.contacts, report.participants = len(users)-1, len(users)
                messages, chats, ids = [], {}, set()
                for index, row in enumerate(extractor.messages(), 1):
                    report.messages_total += 1
                    try:
                        kind = row["type"]
                        if type(kind) is not int or kind not in profile["text_types"] + profile["unsupported_types"]:
                            raise AndroidSourceError("unknown_message_type", f"第{index}条消息类型未知，不能强行解析")
                        group = isinstance(row["talker"], str) and row["talker"].endswith(profile["group_suffix"])
                        if kind not in profile["text_types"] or group:
                            label = "group" if group else str(kind)
                            report.skipped_unsupported_count += 1
                            report.skipped_by_type[label] = report.skipped_by_type.get(label, 0) + 1
                            continue
                        message, chat = map_text_message(row, index, metadata["account"]["wxid"], users, profile)
                        if message["id"] in ids:
                            raise AndroidSourceError("duplicate_message_id", f"第{index}条消息局部 ID 重复")
                        ids.add(message["id"])
                        messages.append(message)
                        chats[chat["id"]] = chat
                    except AndroidSourceError as exc:
                        report.failed += 1
                        report.issues.append({"index":index, "msg_id":row.get("id"), "code":exc.code, "message":str(exc)})
                report.text_messages = len(messages)
            # 只有所有受支持文本均合法才提供可导入文档，避免隐藏解析错误。
            if report.failed:
                return AndroidParseResult(report)
            report.status = "success"
            exchange = {"format":"chat-exchange", "format_version":"1.0", "source":{"id":namespace, "name":"Android SQLite 文本快照", "account_id":metadata["account"]["wxid"], "metadata":{"adapter":"android-sqlite", "schema_profile":profile["id"], "time_unit":profile["time_unit"], "simulation":report.simulation, "parse_report":report.to_dict()}}, "users":list(users.values()), "chats":list(chats.values()), "messages":messages, "media":[]}
            validation = validate_document(exchange)
            if validation.issues:
                raise AndroidSourceError("exchange_invalid", "转换结果未通过既有 Validator：" + validation.issues[0].message)
            self._users, self._messages = list(users.values()), messages
            return AndroidParseResult(report, LoadedDocument(exchange))
        except (DocumentError, sqlite3.Error, OSError, ValueError) as exc:
            report.status = "failed"
            report.failed += 1
            report.issues.append({"index":None, "code":getattr(exc, "code", "parse_failed"), "message":str(exc)})
            return AndroidParseResult(report)

    def export_exchange(self):
        result = self.parse()
        if result.document is None:
            raise AndroidSourceError("parse_failed", "Android 解析失败：" + result.report.issues[0]["message"])
        return result.document
