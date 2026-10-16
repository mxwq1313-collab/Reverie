import json

from .base_importer import BaseImporter
from .records import LoadedDocument
from .validator import DocumentError


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(f"JSON 对象含重复字段：{key}")
        result[key] = value
    return result


def _invalid_number(value):
    raise DocumentError(f"JSON 不允许非有限数值：{value}")


class JSONImporter(BaseImporter):
    format_name = "json"

    def load(self, path):
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle, object_pairs_hook=_unique_keys, parse_constant=_invalid_number)
        except json.JSONDecodeError as exc:
            raise DocumentError(f"JSON 第{exc.lineno}行第{exc.colno}列无法解析：{exc.msg}") from exc
        return LoadedDocument(payload)
