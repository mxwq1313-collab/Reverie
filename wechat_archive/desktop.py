"""Windows 打包入口和隔离的发布诊断；复用原窗口和数据管线。"""

import argparse
from contextlib import ExitStack
from importlib.resources import files
import json
import os
from pathlib import Path
import sys
import tkinter as tk
import time
from tkinter import messagebox

from . import __version__
from .database.db import default_data_dir
from .errors import ArchiveError, ConflictError, ValidationError
from .exporter import export_readable
from .exporter.readable import _local_path
from .ui.import_controller import ImportController, inspect_archive
from .ui.import_window import ImportWindow
from .ui.application_window import ApplicationWindow
from .ui.application_controller import ApplicationController
from .agent import ArchiveScope, ArchiveTools
from .agent.client import INSTRUCTIONS


def resources_report():
    required = {'wechat_archive.database':['init.sql'], 'wechat_archive.importer':['schemas/chat-exchange-v1.schema.json'],
                'wechat_archive.migration':['sql/002_import_engine.sql'],
                'wechat_archive.web':['static/index.html','static/app.css','static/app.js','static/favicon.svg']}
    result = {}
    for package, paths in required.items():
        for path in paths:
            resource = files(package).joinpath(path)
            if not resource.is_file():
                raise ConflictError('软件缺少必要资源：'+package+'/'+path)
            result[package+'/'+path] = len(resource.read_bytes())
    return result


def smoke_check(source, folder):
    """仅由发布检查显式调用；读取调用者提供的测试/真实导出，不自称获取微信。"""
    folder = _local_path(folder)
    if folder.exists():
        raise ConflictError('诊断目录必须是新目录')
    folder.mkdir(parents=True)
    try:
        return _check_in_directory(source,folder)
    except Exception as error:
        with (folder/'desktop_error.json').open('x',encoding='utf-8') as handle:
            json.dump({'status':'failed','error_type':type(error).__name__,'error':str(error)},handle,ensure_ascii=False,indent=2)
        raise


def _check_in_directory(source,folder):
    resources = resources_report()
    controller = ImportController(report_dir=folder/'import_logs')
    database = folder/'archive.db'
    preview = controller.preview(source, database)
    first, _ = controller.import_data(source, database)
    second, _ = controller.import_data(source, database)
    if first.status != 'success' or second.status != 'success' or first.success_count != preview['messages'] or second.success_count != 0 or second.duplicated_count != first.success_count:
        raise ConflictError('诊断导入/重复校验未通过')
    exported = export_readable(database, folder/'readable')
    if exported['messages'] != first.success_count:
        raise ConflictError('诊断导出条数不一致')
    root = tk.Tk(); root.withdraw()
    app = ApplicationWindow(root, controller=ApplicationController(folder/'ui_state'),archive=database)
    try:
        root.update_idletasks(); root.update()
        ui = {'title':root.title(), 'export_button':str(app.export_button['text']), 'browse_button_enabled':app.controller.database is not None,'pages':list(app.pages),'in_app_messages':len(app.message_rows)}
    finally:
        app.close()
    report = {'status':'passed', 'version':__version__, 'frozen':bool(getattr(sys,'frozen',False)),
              'runtime_prefix':sys.prefix, 'data_directory':str(default_data_dir()), 'resources':resources,
              'messages':first.success_count,'duplicates':second.duplicated_count,'exported':exported['messages'],
              'retained':first.source_metadata.get('metadata',{}).get('external_parse',{}).get('quarantined_count',0),
              'ui':ui, 'browser_opened':False,'source_acquisition_used':False}
    (folder/'desktop_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


def codex_smoke_check(folder):
    """显式发布诊断：仅自建一条记录和独立无登录账号，不发推理。"""
    folder = _local_path(folder)
    if folder.exists():raise ConflictError('Codex 发布诊断目录必须是新目录。')
    folder.mkdir(parents=True)
    from .services import ChatService
    service = ChatService(folder/'unit_archive.db')
    owner = service.create_user(wxid='release_unit_owner',nickname='测试自己')
    peer = service.create_user(wxid='release_unit_peer',nickname='测试对方')
    service.create_message(sender_id=owner.id,receiver_id=peer.id,content='发布诊断：自建记录。',create_time='2026-10-13T00:00:00Z')
    root = tk.Tk();root.withdraw()
    app = ApplicationWindow(root,controller=ApplicationController(folder/'profile'),archive=folder/'unit_archive.db')
    try:
        app.show_page('Codex 助手');panel=app.agent_panel
        panel.connect_button.invoke();deadline=time.monotonic()+35
        while panel.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        root.update()
        if panel.busy or not panel.client.connected or '未登录' not in panel.account_text.get():raise ConflictError('EXE Codex 连接诊断未通过。')
        scope=panel.current_scope();tools=ArchiveTools(scope)
        response=panel.client.request('thread/start',{'cwd':str(panel.client.workspace),'approvalPolicy':'on-request','sandbox':'read-only',
            'ephemeral':True,'baseInstructions':INSTRUCTIONS,'developerInstructions':INSTRUCTIONS,'dynamicTools':tools.specs()})
        model_count=len(panel.client.models())
        login=panel.client.login();panel.client.cancel_login()
        result={'status':'passed','version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
            'pages':list(app.pages),'selected_page':app.current_page,'login_button':str(panel.login_button['text']),
            'official_initialize_account_read':True,'isolated_unlogged_account':True,'dynamic_tools_registered':len(tools.specs()),
            'instruction_sources':response.get('instructionSources',[]),'model_catalog_count':model_count,
            'official_login_start_cancel':True,'local_tool_messages':tools.execute('archive_overview',{})['messages'],
            'browser_opened':False,'real_chat_read':False,'real_inference':False}
        (folder/'codex_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    finally:app.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='思绪 · 本地聊天归档')
    parser.add_argument('--archive',type=Path,help='可选：打开已有归档库')
    parser.add_argument('--smoke-check',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--check-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--wechat-worker',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--worker-result',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--codex-check-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--knowledge-check-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--sixu-check-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--workbench-check-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--workbench-preview-dir',type=Path,help=argparse.SUPPRESS)
    parser.add_argument('--page',choices=(*ApplicationWindow.PAGE_NAMES,*ApplicationWindow.LEGACY_NAMES),help='打开指定软件页面')
    options = parser.parse_args(argv)
    check_folder=options.check_dir or options.workbench_check_dir or options.codex_check_dir or options.knowledge_check_dir or options.sixu_check_dir
    check_existed=bool(check_folder and Path(check_folder).exists())
    with ExitStack() as stack:
        original = sys.stdout,sys.stderr
        try:
            if sys.stdout is None:sys.stdout = stack.enter_context(open(os.devnull,'w',encoding='utf-8'))
            if sys.stderr is None:sys.stderr = stack.enter_context(open(os.devnull,'w',encoding='utf-8'))
            if options.wechat_worker:
                if options.worker_result is None:raise ValidationError('读取工作进程缺少结果路径。')
                from .wechat_source.live_source import worker_main
                return worker_main(options.wechat_worker,options.worker_result)
            if options.sixu_check_dir:
                from .ui.v1_release_check import v1_check
                v1_check(options.sixu_check_dir)
                return 0
            if options.knowledge_check_dir:
                from .knowledge.release_check import knowledge_check
                knowledge_check(options.knowledge_check_dir)
                return 0
            if options.codex_check_dir:
                codex_smoke_check(options.codex_check_dir)
                return 0
            if options.workbench_check_dir or options.workbench_preview_dir:
                from .ui.release_check import workbench_check
                workbench_check(options.workbench_check_dir or options.workbench_preview_dir,preview=options.workbench_preview_dir is not None)
                return 0
            if options.smoke_check:
                if options.check_dir is None:raise ValidationError('发布诊断需要明确的新目录')
                smoke_check(options.smoke_check,options.check_dir)
                return 0
            if getattr(sys,'frozen',False):os.chdir(Path(sys.executable).parent)
            root = tk.Tk();root.withdraw();app = ApplicationWindow(root,data_dir=default_data_dir(),archive=options.archive)
            if options.page:app.show_page(options.page)
            root.after_idle(root.deiconify)
            root.mainloop()
            return 0
        except Exception as error:
            if check_folder and not check_existed and Path(check_folder).is_dir():
                import traceback
                try:
                    with (Path(check_folder)/'check_error.json').open('x',encoding='utf-8') as handle:
                        json.dump({'error_type':type(error).__name__,'error':str(error),'traceback':traceback.format_exc()},handle,ensure_ascii=False,indent=2)
                except OSError:pass
            if not options.sixu_check_dir and not options.smoke_check and not options.wechat_worker and not options.codex_check_dir and not options.knowledge_check_dir and not options.workbench_check_dir and not options.workbench_preview_dir:
                messagebox.showerror('思绪无法启动',str(error) if isinstance(error,ArchiveError) else '启动失败，请确认软件文件夹已完整解压。')
            return 1
        finally:
            sys.stdout,sys.stderr=original


if __name__=='__main__':raise SystemExit(main())
