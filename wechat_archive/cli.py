"""无需额外依赖的命令行接口，结果以 UTF-8 JSON 输出。"""

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from . import __version__
from .database.db import SCHEMA_VERSION, default_data_dir
from .demo import seed_demo
from .errors import ArchiveError, ConflictError
from .services import ChatService
from .importer import CSVImporter, JSONImporter, ReportWriteError


def _json_default(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"无法序列化 {type(value).__name__}")


def _emit(value, *, stream=None) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=_json_default), file=stream or sys.stdout)


def _add_page(parser) -> None:
    parser.add_argument("--limit", type=int, default=100, help="每页条数，1–1000，默认 100")
    parser.add_argument("--offset", type=int, default=0, help="跳过的条数，默认 0")


def _add_filters(parser, *, contacts=True, keyword=True) -> None:
    if contacts:
        parser.add_argument("--user", type=int, dest="user_id", help="查询此联系人的发送和接收消息")
        parser.add_argument("--peer", type=int, dest="peer_id", help="与 --user 一起限定双向会话")
    if keyword:
        parser.add_argument("--keyword", help="区分大小写的字面关键词")
    parser.add_argument("--start", dest="start_time", help="起始时间（含），需要时区")
    parser.add_argument("--end", dest="end_time", help="结束时间（不含），需要时区")
    _add_page(parser)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="本地聊天归档：数据管理与聊天浏览器")
    parser.add_argument("--version", action="version", version=f"wechat-archive {__version__}")
    parser.add_argument("--db", type=Path, help="数据库路径，放在子命令前；默认 data/chat.db，demo 默认 data/demo.db")
    commands = parser.add_subparsers(dest="command", required=True)
    from .knowledge.cli import add_parser as add_knowledge_parser
    add_knowledge_parser(commands)
    commands.add_parser("init", help="初始化数据库（可重复执行）")
    commands.add_parser("stats", help="查询联系人和消息数量")
    commands.add_parser("demo", help="创建或查看独立的虚构演示库")
    commands.add_parser("migrate", help="备份并升级受支持的旧库，查询迁移记录")
    upgrading = commands.add_parser("upgrade-copy", help="验证Schema1/2归档并创建独立Schema3副本，原库保留")
    upgrading.add_argument("source", type=Path)
    upgrading.add_argument("target", type=Path, help="新目标文件，不覆盖；旧版软件不能打开Schema3")
    snapshots = commands.add_parser("import-snapshot", help="向Schema3副本分批导入选定私聊封存快照，自动恢复未完成会话")
    snapshots.add_argument("source", type=Path)
    snapshots.add_argument("--report-dir", type=Path)
    snapshots.add_argument("--batch-size", type=int, default=1000)
    snapshots.add_argument("--batch-bytes", type=int, default=8*1024*1024)
    snapshots.add_argument("--restart", action="store_true", help="明确重新核对全快照，保留已提交消息并按来源身份去重")
    commands.add_parser("import-ui", help="打开中文导入窗口，选择文件并查看结果")
    exporting = commands.add_parser('export-readable', help='只读导出归档中的文本为离线 HTML/TXT')
    exporting.add_argument('output', type=Path, help='新的保存目录，不覆盖已有目录')
    exporting.add_argument('--format', choices=('both', 'html', 'txt'), default='both')
    exporting.add_argument('--user', type=int, dest='user_id', help='可选：限定查看身份')
    exporting.add_argument('--peer', type=int, dest='peer_id', help='可选：与 --user 一起限定双向会话')
    exporting.add_argument('--timezone', default='+08:00', help='显示时区，默认 +08:00；不修改数据库原时间')
    importing = commands.add_parser("import", help="导入标准 JSON 或简单 CSV，并保存报告")
    importing.add_argument("file", type=Path)
    importing.add_argument("--format", choices=("json", "csv"), dest="import_format", help="默认按 .csv 扩展名选择 CSV，其余按 JSON 读取")
    importing.add_argument("--strict", action="store_true", help="任何记录出错即拒绝整份文件")
    importing.add_argument("--report-dir", type=Path, help="报告目录，默认项目 import_logs/")
    importing.add_argument("--namespace", default="default", help="CSV 身份命名空间，默认 default")
    importing.add_argument("--timezone", default="+08:00", help="CSV 无时区时间的固定偏移，默认 +08:00")
    wechat = commands.add_parser("wechat", help="微信真实结构化导入及备份分析")
    wechat_commands = wechat.add_subparsers(dest="wechat_action", required=True)
    acquire=wechat_commands.add_parser('acquire-export',help='隔离调用已审查 Windows 工具，获取一个真实双向私聊 JSON')
    acquire.add_argument('output',type=Path)
    acquire.add_argument('--tool-python',type=Path,required=True,help='装有 wechatauto-replica 1.2.6.1 的独立 Python 环境')
    acquire.add_argument('--peer',help='稳定 wxid；不指定时选择可核验的近期双向私聊')
    acquire.add_argument('--limit',type=int,default=50)
    acquire.add_argument('--workdir',type=Path,help='工作明文副本位置，必须独立于原微信数据')
    wechat_import = wechat_commands.add_parser("import", help="适配为标准格式并复用现有导入引擎")
    wechat_import.add_argument("file", type=Path)
    wechat_import.add_argument("--adapter", choices=("auto", "mock", "backup", "android","external"), default="auto", help="external 接收登记的真实结构化导出；backup 仅分析")
    wechat_import.add_argument("--strict", action="store_true")
    wechat_import.add_argument("--report-dir", type=Path)
    wechat_convert = wechat_commands.add_parser("convert", help="只转换为标准 JSON，不写数据库")
    wechat_convert.add_argument("file", type=Path)
    wechat_convert.add_argument("--adapter", choices=("auto", "mock", "backup", "android","external"), default="auto")
    wechat_convert.add_argument("--output", type=Path, help="保存为新的 UTF-8 JSON 文件；省略则输出标准 JSON")
    wechat_detect = wechat_commands.add_parser("detect", help="只读检测来源类型和当前支持状态")
    wechat_detect.add_argument("file", type=Path)
    wechat_inspect = wechat_commands.add_parser("inspect-backup", help="只读检查 RMFH 备份结构，消息正文不写库")
    wechat_inspect.add_argument("file", type=Path)
    wechat_inspect.add_argument("--report-dir", type=Path, help="可选：把检查报告保存到备份之外的目录")
    wechat_analyze = wechat_commands.add_parser("analyze-backup", help="只读输出文件结构、逐文件头分析和解析接口报告")
    wechat_analyze.add_argument("file", type=Path)
    wechat_analyze.add_argument("--report-dir", type=Path, help="保存三个报告，默认项目 import_logs/；不覆盖已有报告")
    wechat_header = wechat_commands.add_parser("rmfh-header", help="只读解析单个 RMFH 外壳、头字段与正文区间")
    wechat_header.add_argument("file", type=Path)
    payload_study=wechat_commands.add_parser("study-payload",help="有界元信息 wire 探测、消息包/索引载荷取样和解码评估")
    payload_study.add_argument("file",type=Path)
    payload_study.add_argument("--report-dir",type=Path)
    payload_study.add_argument("--samples-per-pattern",type=int,default=2,help="每模式选 1–4 个较小消息包，默认 2")
    payload_study.add_argument("--sample-bytes",type=int,default=65536,help="单文件正文/元信息读取上限，最多 65536 字节")
    payload_study.add_argument("--total-bytes",type=int,default=4194304,help="正文及元信息总读取预算，最多 16 MiB")
    android = commands.add_parser("android", help="登记 Schema 的 Android 离线明文 SQLite 框架")
    android_commands = android.add_subparsers(dest="android_action", required=True)
    android_detect = android_commands.add_parser("detect", help="检测来源，候选不等于可解析")
    android_detect.add_argument("file", type=Path)
    android_parse = android_commands.add_parser("parse", help="只读解析并输出报告，不写归档库")
    android_parse.add_argument("file", type=Path)
    android_parse.add_argument("--output", type=Path, help="成功时保存标准交换 JSON，必须为新文件")
    android_structure = android_commands.add_parser("schema", help="只读列出 SQLite 表和字段，不做微信身份推断")
    android_structure.add_argument("file", type=Path)
    serve = commands.add_parser("serve", help="启动仅供本机使用的聊天网页")
    serve.add_argument("--demo", action="store_true", help="查看独立的虚构演示库")
    serve.add_argument("--open", action="store_true", dest="open_browser", help="自动打开浏览器")
    serve.add_argument("--port", type=int, default=8765, help="默认 8765；0 表示自动选择可用端口")

    user = commands.add_parser("user", help="联系人增删改查")
    users = user.add_subparsers(dest="action", required=True)
    add = users.add_parser("add", help="新增联系人")
    add.add_argument("wxid")
    add.add_argument("nickname")
    add.add_argument("--avatar")
    get = users.add_parser("get", help="按 ID 查询联系人")
    get.add_argument("id", type=int)
    listing = users.add_parser("list", help="列出联系人")
    _add_page(listing)
    update = users.add_parser("update", help="修改联系人")
    update.add_argument("id", type=int)
    update.add_argument("--wxid")
    update.add_argument("--nickname")
    avatars = update.add_mutually_exclusive_group()
    avatars.add_argument("--avatar")
    avatars.add_argument("--clear-avatar", action="store_true")
    delete = users.add_parser("delete", help="删除没有关联消息的联系人")
    delete.add_argument("id", type=int)

    message = commands.add_parser("message", help="消息增删改查")
    messages = message.add_subparsers(dest="action", required=True)
    add = messages.add_parser("add", help="新增文本消息")
    add.add_argument("sender_id", type=int)
    add.add_argument("receiver_id", type=int)
    add.add_argument("content")
    add.add_argument("--time", dest="create_time", help="例如 2026-01-01T12:00:00+08:00；省略时取当前时间")
    get = messages.add_parser("get", help="查询一条消息")
    get.add_argument("id", type=int)
    listing = messages.add_parser("list", help="按时间列出或筛选消息")
    _add_filters(listing)
    update = messages.add_parser("update", help="修改消息")
    update.add_argument("id", type=int)
    update.add_argument("--sender", type=int, dest="sender_id")
    update.add_argument("--receiver", type=int, dest="receiver_id")
    update.add_argument("--content")
    update.add_argument("--time", dest="create_time")
    delete = messages.add_parser("delete", help="删除指定消息")
    delete.add_argument("id", type=int)

    conversation = commands.add_parser("conversation", help="查询两个人的双向聊天")
    conversation.add_argument("user_id", type=int)
    conversation.add_argument("peer_id", type=int)
    _add_filters(conversation, contacts=False)
    search = commands.add_parser("search", help="按字面关键词搜索消息")
    search.add_argument("keyword")
    _add_filters(search, keyword=False)
    return parser


def _filters(args) -> dict:
    names = ("user_id", "peer_id", "keyword", "start_time", "end_time", "limit", "offset")
    return {name: getattr(args, name) for name in names if hasattr(args, name)}


def _run(args):
    path = args.db
    if path is None and args.command == "demo":
        path = default_data_dir() / "demo.db"
    service = ChatService(path)
    if args.command == "migrate":
        with service.database.connection() as conn:
            history = [dict(row) for row in conn.execute("SELECT * FROM migration_history ORDER BY version")]
            actual_version = conn.execute("PRAGMA user_version").fetchone()[0]
        return {"database": service.database.path, "schema_version": actual_version, "backup": service.database.last_backup_path, "history": history}
    if args.command == "init":
        with service.database.connection() as conn:
            actual_version = conn.execute("PRAGMA user_version").fetchone()[0]
        return {"database": service.database.path, "schema_version": actual_version, "status": "ready"}
    if args.command == "stats":
        return {"database": service.database.path, **service.stats()}
    if args.command == "demo":
        created = seed_demo(service)
        return {
            "database": service.database.path,
            "created": created,
            "stats": service.stats(),
            "users": service.list_users(),
            "conversation_1_2": service.get_conversation(1, 2),
            "search_开会": service.search_messages("开会"),
        }
    if args.command == "conversation":
        return service.list_messages(**_filters(args))
    if args.command == "search":
        return service.list_messages(**_filters(args))
    if args.command == "user":
        if args.action == "add":
            return service.create_user(args.wxid, args.nickname, args.avatar)
        if args.action == "get":
            return service.get_user(args.id)
        if args.action == "list":
            return service.list_users(limit=args.limit, offset=args.offset)
        if args.action == "update":
            fields = {name: getattr(args, name) for name in ("wxid", "nickname") if getattr(args, name) is not None}
            if args.clear_avatar:
                fields["avatar"] = None
            elif args.avatar is not None:
                fields["avatar"] = args.avatar
            return service.update_user(args.id, **fields)
        service.delete_user(args.id)
    elif args.command == "message":
        if args.action == "add":
            return service.create_message(args.sender_id, args.receiver_id, args.content, create_time=args.create_time)
        if args.action == "get":
            return service.get_message(args.id)
        if args.action == "list":
            return service.list_messages(**_filters(args))
        if args.action == "update":
            fields = {name: getattr(args, name) for name in ("sender_id", "receiver_id", "content", "create_time") if getattr(args, name) is not None}
            return service.update_message(args.id, **fields)
        service.delete_message(args.id)
    return {"deleted": args.id, "entity": args.command}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        if args.command == 'knowledge':
            from .knowledge.cli import execute as knowledge_execute
            result,code=knowledge_execute(args)
            if result is not None: _emit(result)
            return code
        elif args.command == "import-snapshot":
            if args.db is None:raise ConflictError('请明确指定 --db Schema3升级副本')
            from .importer.snapshot_importer import SnapshotImporter
            report=SnapshotImporter(args.db,report_dir=args.report_dir).import_snapshot(args.source,batch_size=args.batch_size,max_bytes=args.batch_bytes,restart=args.restart)
            _emit(report.to_dict())
            return {'success':0,'partial':2,'cancelled':2,'failed':1}[report.status]
        elif args.command == "upgrade-copy":
            from .migration.copy_upgrade import upgrade_archive_copy
            _emit(upgrade_archive_copy(args.source, args.target))
            return 0
        elif args.command == "import-ui":
            from .ui.import_window import main as open_import_window
            return open_import_window()
        elif args.command == 'export-readable':
            from .exporter import export_readable
            formats = ('html', 'txt') if args.format == 'both' else (args.format,)
            _emit(export_readable(args.db, args.output, user_id=args.user_id, peer_id=args.peer_id, formats=formats, display_timezone=args.timezone))
            return 0
        elif args.command == "android":
            from .wechat_adapter.android import AndroidWeChatParser, SQLiteDatabaseReader, detect_android_source
            if args.android_action == "detect":
                detected = detect_android_source(args.file)
                _emit(asdict(detected))
                return 0 if detected.status == "candidate" else 1
            if args.android_action == "schema":
                from .wechat_adapter.android.detector import local_path
                source = local_path(args.file)
                if source.is_dir():
                    detected = detect_android_source(source, probe_header=False)
                    if not detected.database:
                        raise ArchiveError(detected.reason)
                    source = Path(detected.database)
                with SQLiteDatabaseReader(source) as reader:
                    structure = reader.schema_report()
                _emit(structure)
                return 0
            result = AndroidWeChatParser(args.file).parse()
            output = result.report.to_dict()
            if result.document is not None and args.output is not None:
                target = args.output.expanduser().resolve()
                if target.exists():
                    raise ConflictError("Android 输出不能覆盖来源或已有文件，请指定新路径")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(result.document.payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                output["output"] = str(target)
            _emit(output)
            return 0 if result.document is not None else 1
        elif args.command == "wechat":
            from .wechat_adapter import WeChatImporter, detect_source, select_adapter
            if args.wechat_action=='acquire-export':
                from .wechat_source.acquisition import run_worker
                _emit(run_worker(args.tool_python,args.output,peer=args.peer,limit=args.limit,workdir=args.workdir))
                return 0
            if args.wechat_action == "study-payload":
                from .wechat_adapter.backup import RMFHPayloadStudy
                from .importer.base_importer import default_report_dir
                report=RMFHPayloadStudy(args.file,samples_per_pattern=args.samples_per_pattern,sample_bytes=args.sample_bytes,total_bytes=args.total_bytes).analyze()
                report.save(args.report_dir if args.report_dir is not None else default_report_dir())
                _emit(report.overview())
                return {"success":0,"partial":2,"failed":1}[report.status]
            if args.wechat_action == "analyze-backup":
                from .wechat_adapter.backup import RMFHFormatAnalyzer
                from .importer.base_importer import default_report_dir
                report = RMFHFormatAnalyzer(args.file).analyze()
                report.save(args.report_dir if args.report_dir is not None else default_report_dir())
                _emit(report.overview())
                return {"success":0, "partial":2, "unsupported":1, "failed":1}[report.status]
            if args.wechat_action == "rmfh-header":
                from .wechat_adapter.backup import parse_container
                _emit(parse_container(args.file).to_dict())
                return 0
            if args.wechat_action == "inspect-backup":
                from .wechat_adapter import BackupAdapter
                report = BackupAdapter().inspect(args.file)
                if args.report_dir is not None:
                    report.save(args.report_dir)
                _emit(report.to_dict())
                return 0 if report.inspection_status == "recognized" else 1
            if args.wechat_action == "import":
                report = WeChatImporter(args.db, adapter=args.adapter, strict=args.strict, report_dir=args.report_dir).import_file(args.file)
                _emit(report.to_dict())
                return {"success": 0, "partial": 2, "failed": 1}[report.status]
            if args.wechat_action == "detect":
                detected = detect_source(args.file)
                _emit(asdict(detected))
                return 0 if detected.supported else 1
            from .importer.validator import DocumentError, validate_document
            loaded = select_adapter(args.file, args.adapter).export_exchange(args.file)
            validated = validate_document(loaded.payload)
            if validated.issues:
                raise DocumentError("转换文档未通过当前 Validator：" + "; ".join(issue.message for issue in validated.issues[:3]))
            if args.output is None:
                _emit(loaded.payload)
            else:
                target = args.output.expanduser().resolve()
                source = args.file.expanduser().resolve()
                source = source / "export.json" if source.is_dir() else source
                if target == source or target.exists():
                    raise ConflictError("转换输出不能覆盖来源或已有文件，请指定新的输出路径")
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("x", encoding="utf-8", newline="\n") as handle:
                    json.dump(loaded.payload, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                _emit({"output": target, "format": "chat-exchange", "format_version": "1.0", "users": len(validated.users), "chats": len(validated.chats), "messages": len(validated.messages)})
            return 0
        elif args.command == "import":
            kind = args.import_format or ("csv" if args.file.suffix.lower() == ".csv" else "json")
            options = dict(report_dir=args.report_dir, strict=args.strict)
            if kind == "csv":
                importer = CSVImporter(args.db, namespace=args.namespace, timezone=args.timezone, **options)
            else:
                importer = JSONImporter(args.db, **options)
            report = importer.import_file(args.file)
            _emit(report.to_dict())
            return {"success": 0, "partial": 2, "failed": 1}[report.status]
        elif args.command == "serve":
            from .web.server import run_server
            run_server(args.db, port=args.port, demo=args.demo, open_browser=args.open_browser)
        else:
            _emit(_run(args))
    except ReportWriteError as exc:
        result = exc.report.to_dict()
        result["report_error"] = str(exc)
        _emit(result)
        return 1
    except (ArchiveError, sqlite3.Error, OSError) as exc:
        _emit({"error": {"type": type(exc).__name__, "message": str(exc)}}, stream=sys.stderr)
        return 1
    return 0
