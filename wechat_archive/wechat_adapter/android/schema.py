import hashlib
import json
from importlib.resources import files

from .errors import AndroidSourceError

PROFILES = {"enmicromsg-legacy-text-v1": "legacy_text_v1.json"}


def affinity(declared):
    value = declared.upper()
    if "INT" in value:
        return "INTEGER"
    if any(word in value for word in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if not value or "BLOB" in value:
        return "BLOB"
    if any(word in value for word in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def load_profile(name):
    if name not in PROFILES:
        raise AndroidSourceError("unknown_schema", "未登记的 Android Schema，禁止自动猜测映射")
    return json.loads(files("wechat_archive.wechat_adapter.android").joinpath("profiles", PROFILES[name]).read_text(encoding="utf-8"))


def validate_schema(profile, report, metadata):
    if metadata["time_unit"] != profile["time_unit"]:
        raise AndroidSourceError("time_unit_mismatch", "声明的时间单位与登记 Schema 不一致")
    projected = {}
    for entity in ("contacts", "messages"):
        mapping = profile[entity]
        table = mapping["table"]
        info = report["tables"].get(table)
        if info is None or info["virtual"]:
            raise AndroidSourceError("missing_table", f"登记 Schema 需要普通表 {table}，不接受缺失表或虚拟表")
        columns = {row["name"]: row for row in info["columns"]}
        for field, expected in mapping["required"].items():
            if field not in columns:
                raise AndroidSourceError("missing_field", f"{table} 缺少字段 {field}")
            if affinity(columns[field]["type"]) != expected:
                raise AndroidSourceError("field_type", f"{table}.{field} 类型不匹配登记 Schema")
        for field, expected in mapping["optional"].items():
            if field in columns and affinity(columns[field]["type"]) != expected:
                raise AndroidSourceError("field_type", f"可选字段 {table}.{field} 类型不匹配")
        projected[entity] = {key: column for key, column in mapping["fields"].items() if column in columns}
    signature = hashlib.sha256(json.dumps(report["tables"], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return projected, signature
