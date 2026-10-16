import json
import re
import os
from dataclasses import dataclass, field
from pathlib import Path

from ...importer.json_importer import _invalid_number, _unique_keys
from ...importer.validator import FieldError, fields, text
from .errors import AndroidSourceError

METADATA_NAME = "android_source.json"
SQLITE_HEADER = b"SQLite format 3\x00"


def local_path(value, *, must_exist=True):
    if not isinstance(value, (str, os.PathLike)):
        raise AndroidSourceError("illegal_path", "路径必须是文字或 Path 对象")
    raw = os.fspath(value)
    if not isinstance(raw, str):
        raise AndroidSourceError("illegal_path", "不接受无法确定编码的字节路径")
    scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", raw)
    if not raw or any(ord(char) < 32 for char in raw) or "://" in raw or raw.startswith(("\\\\", "//", "file:")) or scheme and len(scheme.group(1)) > 1:
        raise AndroidSourceError("illegal_path", "输入必须是本机普通路径，不能是 URI、网络路径或控制字符")
    path = Path(value).expanduser()
    if ".." in path.parts or path.is_symlink():
        raise AndroidSourceError("illegal_path", "不接受路径穿越或符号链接，请直接指定快照路径")
    try:
        resolved = path.resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise AndroidSourceError("invalid_path", f"无法解析输入路径：{exc}") from exc
    if must_exist and not resolved.exists():
        raise AndroidSourceError("missing_path", "输入路径不存在")
    return resolved


@dataclass(slots=True)
class DetectedSource:
    type: str = "android_wechat"
    confidence: float = 0.0
    status: str = "failed"
    files: list[str] = field(default_factory=list)
    database: str | None = None
    metadata_file: str | None = None
    micro_msg_layout: bool = False
    sqlite_header: bool | None = None
    reason: str = ""


def detect_android_source(value, *, probe_header=True):
    result = DetectedSource()
    try:
        path = local_path(value)
        candidates = []
        if path.is_file():
            if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
                raise AndroidSourceError("unknown_file", "Android 输入应为 SQLite 文件或 MicroMsg 快照目录")
            candidates = [path]
        elif path.is_dir():
            # 只扫描有限层级，不遍历整个磁盘或任意深度目录。
            dirs = [path]
            micro = path if path.name.lower() == "micromsg" else path / "MicroMsg"
            if micro.is_dir() and not micro.is_symlink():
                dirs.append(micro)
                dirs.extend(child for child in micro.iterdir() if child.is_dir() and not child.is_symlink())
            for folder in dict.fromkeys(dirs):
                file = folder / "EnMicroMsg.db"
                if file.is_file():
                    if file.is_symlink() or not file.resolve().is_relative_to(path):
                        raise AndroidSourceError("illegal_path", "数据库候选不能指向输入目录之外")
                    candidates.append(file.resolve())
        else:
            raise AndroidSourceError("invalid_path", "输入不是普通文件或目录")
        candidates = list(dict.fromkeys(candidates))
        result.files = [str(file) for file in candidates]
        if not candidates:
            raise AndroidSourceError("not_found", "未找到 EnMicroMsg.db 候选；检测不等同于解析")
        if len(candidates) != 1:
            raise AndroidSourceError("ambiguous_source", "发现多个账号数据库，请明确指定一个文件或账号目录")
        database = candidates[0]
        metadata = database.parent / METADATA_NAME
        result.database = str(database)
        result.micro_msg_layout = any(part.lower() == "micromsg" for part in database.parts)
        result.confidence = 0.65 if result.micro_msg_layout else 0.4
        if not metadata.is_file() or metadata.is_symlink():
            raise AndroidSourceError("missing_metadata", "缺少普通文件 android_source.json；不能猜测账号、Schema 或时间单位")
        result.metadata_file = str(metadata)
        result.files.append(str(metadata))
        if probe_header:
            with database.open("rb") as handle:
                result.sqlite_header = handle.read(16) == SQLITE_HEADER
            if not result.sqlite_header:
                raise AndroidSourceError("not_plain_sqlite", "不是明文 SQLite 头：可能加密或未知格式；当前不尝试解密")
        result.confidence = 0.9 if result.micro_msg_layout else 0.8
        result.status = "candidate"
        result.reason = "找到候选快照和元信息，仍需校验元信息及登记的 Schema；检测成功不代表解析成功"
    except (AndroidSourceError, OSError) as exc:
        result.reason = str(exc)
    return result


def load_metadata(path, database):
    try:
        with local_path(path).open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle, object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
        fields(data, ("format", "format_version", "database_file", "schema_profile", "time_unit", "sqlite_snapshot", "account"), ("format", "format_version", "database_file", "schema_profile", "time_unit", "sqlite_snapshot", "account", "database_sha256", "simulation"))
        if data["format"] != "android-wechat-source" or data["format_version"] != "1.0":
            raise AndroidSourceError("metadata_version", "不支持的 Android 来源元信息格式或版本")
        if data["database_file"] != Path(database).name or any(char in str(data["database_file"]) for char in ("/", "\\")):
            raise AndroidSourceError("metadata_binding", "database_file 必须准确绑定当前数据库文件名，不允许路径跳转")
        if data["sqlite_snapshot"] is not True:
            raise AndroidSourceError("snapshot_required", "只能解析明确声明为离线 SQLite 快照的输入")
        fields(data["account"], ("wxid", "nickname"), ("wxid", "nickname"))
        data["account"] = {key: text(data["account"][key], key) for key in ("wxid", "nickname")}
        text(data["schema_profile"], "schema_profile")
        digest = data.get("database_sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest)):
            raise AndroidSourceError("metadata_hash", "database_sha256 必须是 64 位十六进制")
        if "simulation" in data and type(data["simulation"]) is not bool:
            raise AndroidSourceError("metadata_simulation", "simulation 必须是布尔值")
        return data
    except (FieldError, ValueError, OSError) as exc:
        raise AndroidSourceError("invalid_metadata", f"Android 元信息无效：{exc}") from exc
