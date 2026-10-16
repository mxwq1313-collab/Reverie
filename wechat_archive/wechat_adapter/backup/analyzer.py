"""RMFH 文件清单与外壳分析；无数据库、解密或正文处理依赖。"""

import hashlib
import json
import os
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ..base import UnsupportedWeChatSource
from .parser import find_devices
from .reader import checked_path, children, file_stamp, read_edges

DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
CATEGORIES = ("ChatPackage", "Index", "Media", "metadata", "other")
METADATA_NAMES = {"backup.attr", "alt_name.dat", "roam_device_info.dat", "backup_time.dat", "detail.dat",
                  "phoneid.dat", "phone_history.dat", "pkg.attr", "pkg_info.dat", "tar_index.dat", "pkg.lock"}


def parse_header(data):
    """解析可见前缀；字段含义未确认，按偏移和大小命名。"""
    if len(data) < 16 or data[:4] != b"RMFH":
        raise UnsupportedWeChatSource("RMFH 前缀不足 16 字节或标记错误")
    fields = []
    for offset, size in ((4, 4), (8, 2), (10, 2), (12, 4)):
        value = data[offset:offset + size]
        fields.append({"offset":offset, "size":size, "raw_hex":value.hex(),
                       "little_endian":int.from_bytes(value, "little"),
                       "big_endian":int.from_bytes(value, "big"), "meaning":"unverified"})
    return {"magic":"RMFH", "prefix_bytes":16, "prefix_hex":data[:16].hex(), "fields":fields}


@dataclass(frozen=True)
class PayloadSpan:
    offset: int
    length: int
    encoding: str = "unknown"


@dataclass(frozen=True)
class RMFHContainer:
    path: str
    bytes: int
    header: dict
    footer_offset: int
    payload: PayloadSpan
    layout: str = "rmfh-128-envelope-observed"
    content_decoded: bool = False

    def to_dict(self):
        return asdict(self)


def _envelope_from_edges(path, head, tail, stamp):
    header = parse_header(head)
    fields = header["fields"]
    if fields[1]["little_endian"] != 1 or fields[3]["little_endian"] != 0 or fields[2]["little_endian"] & 0xff != 1:
        raise UnsupportedWeChatSource("未知 RMFH 头字段投影，拒绝按现有外壳布局解析")
    if stamp[0] < 256 or len(head) != 128 or len(tail) != 128 or tail[:4] != b"RMFT":
        raise UnsupportedWeChatSource("外壳截断或布局未知，需要 128 字节 RMFH 头和末尾 128 字节 RMFT 尾")
    return RMFHContainer(str(path), stamp[0], header, stamp[0]-128, PayloadSpan(128, stamp[0]-256))


def parse_container(path):
    """真实实现的外壳解析接口，返回正文位置；不读取正文。"""
    path = checked_path(path)
    if path.name.lower() == "enmicromsg.db" or path.suffix.lower() in DATABASE_SUFFIXES:
        raise UnsupportedWeChatSource("RMFH 分析接口不读取数据库文件")
    head, tail, stamp = read_edges(path)
    return _envelope_from_edges(path, head, tail, stamp)


def _category(path):
    parts = {p.lower() for p in path.parts}
    return next((c for c in CATEGORIES[:3] if c.lower() in parts), "metadata" if path.name.lower() in METADATA_NAMES else "other")


@dataclass
class RMFHAnalysis:
    source: str
    scope_kind: str = "unknown"
    status: str = "unsupported"
    analysis_only: bool = True
    import_supported: bool = False
    content_decoded: bool = False
    message_count: int | None = None
    source_stable: bool = False
    inventory_complete: bool = False
    directories: list = field(default_factory=list)
    files: list = field(default_factory=list)
    file_headers: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    report_paths: dict = field(default_factory=dict)

    def structure_report(self):
        return {"report_format":"rmfh-structure", "report_version":"1.0", "source":self.source,
                "scope_kind":self.scope_kind, "status":self.status, "analysis_only":True,
                "source_stable":self.source_stable, "inventory_complete":self.inventory_complete, "summary":self.summary,
                "directories":self.directories, "files":self.files, "issues":self.issues}

    def header_report(self):
        return {"report_format":"rmfh-headers", "report_version":"1.0", "source":self.source,
                "status":self.status, "analysis_only":True, "inventory_complete":self.inventory_complete, "import_supported":False,
                "content_decoded":False, "message_count":None,
                "field_meaning":"unverified; offsets and both endian interpretations are observations",
                "summary":self.summary, "file_headers":self.file_headers, "issues":self.issues}

    def overview(self):
        return {"source":self.source, "scope_kind":self.scope_kind, "status":self.status,
                "analysis_only":True, "import_supported":False, "content_decoded":False,
                "message_count":None, "source_stable":self.source_stable, "inventory_complete":self.inventory_complete,
                "summary":self.summary, "issues":self.issues, "report_paths":self.report_paths}

    def markdown(self):
        counts = self.summary.get("categories", {})
        lines = ["# RMFH 备份格式分析", "", f"来源：`{self.source}`", "",
                 f"分析状态：{self.status}；只读检查稳定性：{self.source_stable}。", "",
                 "本报告只解析目录与容器外壳，实际消息数量尚未知。", "",
                 "| 分类 | 文件 | 字节 | RMFH 标记 | 外壳通过 | 未知/损坏外壳 | 非 RMFH | 数据库跳过 |",
                 "|---|---:|---:|---:|---:|---:|---:|---:|"]
        for category in CATEGORIES:
            row = counts.get(category, {})
            lines.append("| " + category + " | " + " | ".join(str(row.get(k, 0)) for k in ("files", "bytes", "rmfh", "supported_envelopes", "rejected_envelopes", "non_rmfh", "database_skipped")) + " |")
        lines += ["", f"总文件：{self.summary.get('files',0)}；总大小：{self.summary.get('bytes',0)/1_000_000_000:.2f} GB。",
                  f"目录：{self.summary.get('directories',0)}；会话目录候选：{self.summary.get('session_directories',0)}。",
                  f"清单枚举完成：{self.inventory_complete}；文件头实际读取：{self.summary.get('headers_read',0)}。"]
        if self.scope_kind == 'wechat-rmfh-backup':
            lines += ["", "## 目录模式", "", "下列为已识别目录的结构模板；候选目录名称不用于推断账号身份。", "", "```text",
                      "备份根目录/", "└── <顶层账号目录候选>/", "    ├── roam_device_info.dat",
                      "    └── <设备备份目录>/", "        ├── backup.attr", "        ├── alt_name.dat（如存在）",
                      "        └── files/", "            └── <批次>/", "                ├── <批次元信息文件>",
                      "                └── <会话目录候选>/", "                    ├── ChatPackage/",
                      "                    ├── Index/", "                    └── Media/（如存在）", "```"]
        lines += ["", "## 文件头模式", "", "| 前 16 字节 | 文件数 | 分类计数 |", "|---|---:|---|"]
        for pattern in self.summary.get('header_patterns', []):
            counts_text = ', '.join(f"{key}: {value}" for key,value in sorted(pattern['categories'].items()))
            lines.append(f"| `{pattern['prefix_hex']}` | {pattern['files']} | {counts_text} |")
        lines += [
                  "", "## 文件头观测", "", "| 偏移 | 字节 | 当前记录 | 字段含义 |",
                  "|---|---:|---|---|", "| 0 | 4 | RMFH 标记 | 容器标记 |",
                  "| 4 | 4 | 原始十六进制、大小端整数 | 未确认 |",
                  "| 8 | 2 | 原始十六进制、大小端整数 | 未确认 |",
                  "| 10 | 2 | 原始十六进制、大小端整数 | 未确认 |",
                  "| 12 | 4 | 原始十六进制、大小端整数 | 未确认 |",
                  "| 16–127 | 112 | 摘要与非零字节数量，未输出原文 | 未确认 |", "",
                  "已观测外壳使用 128 字节头及固定末尾 128 字节 RMFT 尾。正文区间为 [128, 文件大小−128)。",
                  "不会在未知正文中搜索 RMFT，也不会把字节分布解释为已确认的加密算法。", "",
                  "逐文件路径、目录层次见 structure_report.json；逐文件前缀、外壳边界、模式频率见 header_analysis.json。", "",
                  "## 解析接口", "", "```python", "analyzer = RMFHFormatAnalyzer(source)",
                  "result = analyzer.analyze()", "paths = result.save(output_directory)",
                  "header = parse_header(prefix_bytes)", "container = parse_container(package_path)",
                  "# container.payload.offset / length：外壳内正文区间；encoding='unknown'", "```", "",
                  "未知/截断外壳在 parse_container 中明确抛错；批量分析保留文件级问题并继续生成报告。",
                  "分析状态 success 只表示本次外壳分析通过，不表示可导入聊天或正文已解码。"]
        if self.issues:
            lines += ["", "## 问题", ""] + [f"- {row.get('path','来源')}：{row['message']}" for row in self.issues[:100]]
        return "\n".join(lines)+"\n"

    def save(self, directory):
        directory = Path(directory).expanduser().resolve()
        source = Path(self.source)
        roots = [source.parent if source.is_file() else source]
        roots += [d.parent for d in find_devices(source)]
        if any(directory == root or root in directory.parents for root in roots):
            raise UnsupportedWeChatSource("分析报告不能保存在原备份内部")
        if len(self.files) > 200000:
            raise UnsupportedWeChatSource("报告超过已声明文件上限")
        now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bundle = directory / f"rmfh_analysis_{now}_{uuid4().hex[:12]}"
        bundle.mkdir(parents=True, exist_ok=False)
        self.report_paths = {name:str(bundle/name) for name in ("structure_report.json", "header_analysis.json", "summary.md")}
        documents = {"structure_report.json":json.dumps(self.structure_report(), ensure_ascii=False, indent=2)+"\n",
                     "header_analysis.json":json.dumps(self.header_report(), ensure_ascii=False, indent=2)+"\n",
                     "summary.md":self.markdown()}
        for name, text in documents.items():
            target = bundle / name
            temporary = target.with_suffix(target.suffix+".tmp")
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        return self.report_paths


class RMFHFormatAnalyzer:
    """只读目录与文件头分析器，不创建数据库，不选择 Android 适配器。"""
    def __init__(self, source, *, max_files=200000, max_depth=10):
        self.source = checked_path(source)
        if type(max_files) is not int or not 1 <= max_files <= 200000 or type(max_depth) is not int or not 0 <= max_depth <= 20:
            raise ValueError("分析器上限必须是有效整数：文件 1–200000，深度 0–20")
        self.max_files, self.max_depth = max_files, max_depth

    def analyze_file(self, path):
        path = checked_path(path)
        if self.source.is_dir():
            if path != self.source and self.source not in path.parents:
                raise UnsupportedWeChatSource("待分析文件不在指定来源范围内")
        elif path != self.source:
            raise UnsupportedWeChatSource("单文件分析只能读取指定文件")
        row = {"category":_category(path), "bytes":path.stat().st_size, "status":"non_rmfh", "marker":None,
               "header":None, "payload":None, "footer_offset":None, "reason":"非 RMFH，内容格式未验证"}
        if path.name.lower() == "enmicromsg.db" or path.suffix.lower() in DATABASE_SUFFIXES:
            row.update(status="database_skipped", reason="数据库文件只记录名称和大小，不读取")
            return row
        head, tail, stamp = read_edges(path)
        row["edge_sha256"] = hashlib.sha256(head+tail).hexdigest()
        if head[:4] != b"RMFH":
            return row
        row["marker"] = "RMFH"
        try:
            row["header"] = parse_header(head)
            row["header_block"] = {"observed_bytes":len(head), "sha256":hashlib.sha256(head).hexdigest(),
                                   "bytes_16_127_nonzero":sum(b != 0 for b in head[16:])}
            container = _envelope_from_edges(path, head, tail, stamp)
            row.update(status="supported_envelope", payload=asdict(container.payload),
                       footer_offset=container.footer_offset, footer_marker="RMFT", layout=container.layout,
                       reason="已解析观测外壳；正文含义和编码未知")
        except UnsupportedWeChatSource as exc:
            row.update(status="rejected_envelope", reason=str(exc))
        return row

    def analyze(self):
        result = RMFHAnalysis(str(self.source))
        root = self.source if self.source.is_dir() else self.source.parent
        stamps = {self.source:file_stamp(self.source)}
        try:
            devices = find_devices(self.source) if self.source.is_dir() or self.source.name == "backup.attr" else []
            result.scope_kind = "wechat-rmfh-backup" if devices else "rmfh-file" if self.source.is_file() else "unknown"
            stack = [(self.source, 0)]
            while stack:
                path, depth = stack.pop()
                if depth > self.max_depth:
                    raise UnsupportedWeChatSource("文件层级超过分析上限")
                if path.is_dir():
                    entries = children(path)
                    stamps[path] = file_stamp(path)
                    relative = path.relative_to(root).as_posix()
                    result.directories.append({"path":relative, "depth":depth,
                                               "parent":path.parent.relative_to(root).as_posix() if path != root else None,
                                               "session_candidate":any(p.name == "ChatPackage" and p.is_dir() for p in entries),
                                               "direct_files":sum(p.is_file() for p in entries), "direct_directories":sum(p.is_dir() for p in entries)})
                    stack.extend((p, depth+1) for p in reversed(entries))
                    if len(result.directories) > self.max_files:
                        raise UnsupportedWeChatSource("目录数量超过分析上限")
                    continue
                if not path.is_file():
                    raise UnsupportedWeChatSource("分析范围含非普通文件")
                if len(result.files) >= self.max_files:
                    raise UnsupportedWeChatSource("文件数量超过分析上限")
                stamps[path] = file_stamp(path)
                relative = path.relative_to(root).as_posix()
                category = _category(path)
                result.files.append({"path":relative, "parent":path.parent.relative_to(root).as_posix(),
                                     "category":category, "bytes":stamps[path][0], "mtime_ns":stamps[path][1]})
                row = self.analyze_file(path)
                row["path"] = relative
                result.file_headers.append(row)
                if row["status"] == "rejected_envelope" or row["status"] == "non_rmfh" and (category in {"ChatPackage", "Index"} or path.name.lower() == "backup.attr"):
                    result.issues.append({"path":relative, "code":"unsupported_file_format", "message":row["reason"]})
                if path.name.lower() == "pkg.lock":
                    result.issues.append({"path":relative, "code":"active_backup_lock", "message":"存在 pkg.lock，不能确认离线稳定状态"})
            result.inventory_complete = True
            if any(file_stamp(path) != stamp for path, stamp in stamps.items()):
                raise UnsupportedWeChatSource("来源在分析期间变化，请等待备份结束再检查")
            result.source_stable = not any(i["code"] == "active_backup_lock" for i in result.issues)
            if result.scope_kind == "unknown" or result.scope_kind == "rmfh-file" and not any(r["marker"] == "RMFH" for r in result.file_headers):
                result.status = "unsupported"
            else:
                result.status = "partial" if result.issues else "success"
        except (UnsupportedWeChatSource, OSError) as exc:
            result.status = "failed"
            result.source_stable = False
            result.issues.append({"code":"analysis_failed", "message":str(exc)})
        categories = {c:dict(files=0, bytes=0, rmfh=0, supported_envelopes=0, rejected_envelopes=0, non_rmfh=0, database_skipped=0) for c in CATEGORIES}
        patterns = {}
        for row in result.files:
            categories[row['category']]['files'] += 1
            categories[row['category']]['bytes'] += row['bytes']
        for row in result.file_headers:
            totals = categories[row["category"]]
            totals["rmfh"] += row["marker"] == "RMFH"
            key = {"supported_envelope":"supported_envelopes", "rejected_envelope":"rejected_envelopes"}.get(row["status"], row["status"])
            totals[key] += 1
            if row["header"]:
                prefix = row["header"]["prefix_hex"]
                pattern = patterns.setdefault(prefix, {"prefix_hex":prefix, "fields":row["header"]["fields"], "files":0, "categories":Counter()})
                pattern["files"] += 1
                pattern["categories"][row["category"]] += 1
        result.summary = {"files":len(result.files), "directories":len(result.directories),
                          "headers_read":sum(row['status'] != 'database_skipped' for row in result.file_headers),
                          "bytes":sum(row["bytes"] for row in result.files),
                          "device_directories":len(devices) if 'devices' in locals() else 0,
                          "session_directories":sum(d["session_candidate"] for d in result.directories),
                          "categories":categories, "header_patterns":sorted(patterns.values(), key=lambda r:r["prefix_hex"]),
                          "edge_read_limit_per_file":256, "field_meaning":"unverified"}
        return result
