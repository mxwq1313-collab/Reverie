"""中文 Tk 导入窗口，无需在终端输入命令。"""

import os
import queue
import threading
import tkinter as tk
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from uuid import uuid4

from ..importer import ReportWriteError
from .. import __version__
from ..web.server import make_server
from .import_controller import FORMAT_LABELS, ImportController, default_target, inspect_archive, project_root


def backup_result_text(backup, database, report_path):
    text = ("微信备份结构检查（归档库未写入）\n\n"
            f"结构：{backup['format']}\n会话目录：{backup['session_directories']}\n"
            f"消息包文件：{backup['chat_package_files']}\n索引文件：{backup['index_files']}\n"
            f"媒体文件：{backup['media_files']}\n总大小：{backup['bytes']/1_000_000_000:.2f} GB\n"
            "实际消息数量：尚未解析\n聊天正文：尚不可读取\n\n"
            f"{backup['reason']}\n\n目标归档库：{database}\n报告：{report_path}\n")
    if backup['required_conditions']:
        text += "\n缺少的条件：\n" + "\n".join(backup['required_conditions'])
    return text


class ImportWindow:
    def __init__(self, root, *, controller=None):
        self.root = root
        self.controller = controller or ImportController()
        self.source = tk.StringVar(master=root)
        self.target = tk.StringVar(master=root, value=str(default_target()))
        self.format_label = tk.StringVar(master=root, value=FORMAT_LABELS["auto"])
        self.namespace = tk.StringVar(master=root, value="default")
        self.timezone = tk.StringVar(master=root, value="+08:00")
        self.strict = tk.BooleanVar(master=root, value=False)
        self.status = tk.StringVar(master=root, value="选择来源后，可以先预览，再开始导入。")
        self.events = queue.Queue()
        self.busy = False
        self.last_database = None
        self.last_report = None
        self.blocked_source = None
        self.servers = {}
        self.action_buttons = []
        root.title(f"导入数据 · 聊天归档 {__version__}")
        root.geometry("880x720")
        root.minsize(780, 650)
        root.configure(background="#f2f5f0")
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f2f5f0")
        style.configure("TLabel", background="#f2f5f0", foreground="#263b34", font=("Microsoft YaHei", 10))
        style.configure("Title.TLabel", font=("Microsoft YaHei", 21, "bold"))
        style.configure("Hint.TLabel", foreground="#68786b", font=("Microsoft YaHei", 9))
        style.configure("TButton", font=("Microsoft YaHei", 10), padding=(10, 7))
        style.configure("Primary.TButton", background="#236552", foreground="white")
        style.map("Primary.TButton", background=[("active", "#194f40")])
        style.configure("TCheckbutton", background="#f2f5f0", font=("Microsoft YaHei", 10))
        container = ttk.Frame(root, padding=24)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="导入聊天数据", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="选择本机文件，复用已有校验、去重和导入报告。", style="Hint.TLabel").pack(anchor="w", pady=(6, 18))
        form = ttk.Frame(container)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="数据类型").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=6)
        self.format_box = ttk.Combobox(form, textvariable=self.format_label, values=list(FORMAT_LABELS.values()), state="readonly", width=25)
        self.format_box.grid(row=0, column=1, sticky="w", pady=6)
        self.format_box.bind("<<ComboboxSelected>>", lambda _: self.update_csv_fields())
        self.button(form, "填入示例", self.use_sample).grid(row=0, column=2, columnspan=2, sticky="e", padx=(8, 0))
        ttk.Label(form, text="数据来源").grid(row=1, column=0, sticky="w", pady=8)
        self.source_entry = ttk.Entry(form, textvariable=self.source)
        self.source_entry.grid(row=1, column=1, sticky="ew", pady=8)
        self.button(form, "选择文件", self.choose_file).grid(row=1, column=2, padx=(8, 4))
        self.button(form, "选择文件夹", self.choose_folder).grid(row=1, column=3)
        ttk.Label(form, text="目标归档库").grid(row=2, column=0, sticky="w", pady=8)
        self.target_entry = ttk.Entry(form, textvariable=self.target)
        self.target_entry.grid(row=2, column=1, sticky="ew", pady=8)
        self.button(form, "选择归档库", self.choose_target).grid(row=2, column=2, columnspan=2, sticky="ew", padx=(8, 0))
        options = ttk.Frame(container)
        options.pack(fill="x", pady=(10, 0))
        ttk.Label(options, text="CSV 账户标签").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.namespace_entry = ttk.Entry(options, textvariable=self.namespace, width=19)
        self.namespace_entry.grid(row=0, column=1, padx=(0, 16))
        ttk.Label(options, text="无时区时间按").grid(row=0, column=2, padx=(0, 8))
        self.timezone_entry = ttk.Entry(options, textvariable=self.timezone, width=10)
        self.timezone_entry.grid(row=0, column=3)
        self.strict_box = ttk.Checkbutton(container, text="严格模式：任何记录出错，都不接收整份文件", variable=self.strict)
        self.strict_box.pack(anchor="w", pady=(15, 6))
        ttk.Label(container, text="Android 需明文快照；RMFH 微信备份可检查结构，正文解密与导入尚未支持。", style="Hint.TLabel").pack(anchor="w")
        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(17, 9))
        self.preview_button = self.button(actions, "预览检查", lambda: self.start("preview"))
        self.preview_button.pack(side="left")
        self.import_button = self.button(actions, "开始导入", lambda: self.start("import"), style="Primary.TButton")
        self.import_button.pack(side="left", padx=10)
        self.analysis_button = self.button(actions, "分析 RMFH", lambda: self.start("analysis"))
        self.analysis_button.pack(side="left")
        self.study_button=self.button(actions,"探测载荷",lambda:self.start("payload"))
        self.study_button.pack(side="left",padx=8)
        self.progress = ttk.Progressbar(actions, mode="indeterminate", length=200)
        self.progress.pack(side="right")
        ttk.Label(container, textvariable=self.status, wraplength=800).pack(anchor="w", pady=(2, 8))
        self.result = ScrolledText(container, height=12, wrap="word", font=("Microsoft YaHei", 10), borderwidth=1, relief="solid", background="#fff", foreground="#263b34")
        self.result.pack(fill="both", expand=True)
        self.set_result("导入与分析入口已就绪。\n\n1. 选择数据文件或文件夹。\n2. 微信备份可点击“分析 RMFH”，输出文件结构、文件头和摘要报告，不需要目标归档库。\n3. 导入已支持的数据时，确认归档库，可先预览，再开始导入。\n\n第一次体验可点击“填入示例”，它会使用独立演示库。")
        bottom = ttk.Frame(container)
        bottom.pack(fill="x", pady=(12, 0))
        self.browse_button = ttk.Button(bottom, text="查看已导入的聊天", command=self.open_browser, state="disabled")
        self.browse_button.pack(side="left")
        self.report_button = ttk.Button(bottom, text="打开报告", command=self.open_report, state="disabled")
        self.report_button.pack(side="left", padx=10)
        self.export_button = self.button(bottom, '导出可读文件', self.export_readable_files)
        self.export_button.pack(side='left')
        ttk.Label(bottom, text="数据只保存在本机", style="Hint.TLabel").pack(side="right")
        self.source.trace_add("write", lambda *_: self.source_changed())
        self.update_csv_fields()
        self.poll_job = self.root.after(80, self.poll)

    def button(self, parent, text, command, **options):
        button = ttk.Button(parent, text=text, command=command, **options)
        self.action_buttons.append(button)
        return button

    def chosen(self):
        return next(key for key, label in FORMAT_LABELS.items() if label == self.format_label.get())

    def update_csv_fields(self):
        csv = self.chosen() == "csv" or self.chosen() == "auto" and self.source.get().lower().endswith(".csv")
        mode = "normal" if csv and not self.busy else "disabled"
        self.namespace_entry.configure(state=mode)
        self.timezone_entry.configure(state=mode)

    def source_changed(self):
        if self.blocked_source != self.source.get():
            self.blocked_source = None
            if not self.busy:
                self.import_button.configure(state="normal")
        self.update_csv_fields()

    def choose_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="选择聊天数据文件", initialdir=str(project_root()), filetypes=[("聊天数据", "*.json *.csv *.db *.sqlite *.sqlite3"), ("全部文件", "*.*")])
        if path:
            self.source.set(path)

    def choose_folder(self):
        path = filedialog.askdirectory(parent=self.root, title="选择微信备份、Android 快照或模拟导出文件夹", initialdir=str(project_root()))
        if path:
            self.source.set(path)

    def choose_target(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="选择归档库（已有归档会追加，不重置）", initialdir=str(Path(self.target.get()).parent), initialfile=Path(self.target.get()).name, defaultextension=".db", filetypes=[("SQLite 归档", "*.db")], confirmoverwrite=False)
        if path:
            self.target.set(path)
            self.last_database = None
            if Path(path).is_file():
                try:
                    self.last_database = inspect_archive(path)
                    self.status.set('已有归档已选择，可直接查看聊天或导出可读文件。')
                except Exception:
                    self.status.set('文件已选择，但不是可读取的项目归档；导入前请先检查。')
            self.set_busy(False)

    def use_sample(self):
        chosen = self.chosen()
        if chosen=='external':
            self.status.set('真实导出类型不提供模拟成功样例，请选择来源获取层生成的文件。')
            return
        relative = {"auto":"examples/chat_sample.json", "json":"examples/chat_sample.json", "csv":"examples/chat_sample.csv", "mock":"wechat_mock/export.json", "android":"android_mock", "backup":"examples/rmfh_backup"}[chosen]
        sample = project_root() / relative
        if not sample.exists():
            self.status.set("当前安装位置没有附带示例，请选择自己的文件，或在完整项目文件夹运行。")
            return
        self.source.set(str(sample))
        self.target.set(str(project_root() / "data" / "ui_demo.db"))
        self.source_entry.xview_moveto(1)
        self.target_entry.xview_moveto(1)
        self.status.set("已填入 RMFH 结构模拟示例，只能检查结构，没有聊天正文。" if chosen == "backup" else "已填入示例；将使用独立 ui_demo.db，不混入正式归档库。")

    def set_result(self, text):
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("end", text)
        self.result.configure(state="disabled")

    def set_busy(self, value):
        self.busy = value
        for button in self.action_buttons:
            button.configure(state="disabled" if value else "normal")
        self.import_button.configure(state="disabled" if value or self.blocked_source == self.source.get() else "normal")
        for entry in (self.source_entry, self.target_entry):
            entry.configure(state="disabled" if value else "normal")
        self.format_box.configure(state="disabled" if value else "readonly")
        self.strict_box.configure(state="disabled" if value else "normal")
        self.browse_button.configure(state="disabled" if value or not self.last_database else "normal")
        self.report_button.configure(state="disabled" if value or not self.last_report else "normal")
        self.update_csv_fields()
        self.progress.start(12) if value else self.progress.stop()

    def export_readable_files(self):
        if self.busy:
            return
        database = Path(self.target.get().strip().strip('"')).expanduser()
        if not database.is_absolute():
            database = project_root() / database
        if not database.is_file():
            self.status.set('请先选择已存在的归档库；可读导出不需要重新选择来源文件。')
            return
        parent = filedialog.askdirectory(parent=self.root, title='选择保存位置（自动创建新的聊天导出目录）', initialdir=str(database.parent))
        if not parent:
            return
        stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        folder = Path(parent) / f'聊天导出_{stamp}_{uuid4().hex[:8]}'
        self.start('export', export_folder=folder)

    def start(self, action, *, export_folder=None):
        if self.busy:
            return
        if action == "import" and self.blocked_source == self.source.get():
            self.status.set("这份备份正文尚不可读取，请查看检查报告中的缺失条件。")
            return
        source, target, chosen = self.source.get(), self.target.get(), self.chosen()
        options = dict(strict=self.strict.get(), namespace=self.namespace.get(), timezone=self.timezone.get())
        if action != 'export' and not source.strip():
            self.status.set("请先选择来源文件或文件夹。")
            self.set_result("还没有选择来源。点击“选择文件”或“选择文件夹”，也可以先“填入示例”。")
            return
        if action in {"import", "analysis","payload"}:
            self.last_database = None
            self.last_report = None
        self.set_busy(True)
        self.status.set('正在导出离线 HTML 和 TXT…' if action == 'export' else "正在有界探测元信息和载荷…" if action=="payload" else "正在分析 RMFH 文件结构和文件头…" if action == "analysis" else "正在预览检查…" if action == "preview" else "正在导入，请等待完成…")
        def work():
            try:
                if action == 'export':
                    from ..exporter import export_readable
                    database = Path(target.strip().strip('"')).expanduser()
                    if not database.is_absolute():
                        database = project_root() / database
                    self.events.put(('export', export_readable(database, export_folder)))
                elif action=="payload":
                    self.events.put(("payload",self.controller.study_payload(source)))
                elif action == "analysis":
                    self.events.put(("analysis", self.controller.analyze_backup(source)))
                elif action == "preview":
                    self.events.put(("preview", self.controller.preview(source, target, chosen, **options)))
                else:
                    report, database = self.controller.import_data(source, target, chosen, **options)
                    self.events.put(("import", (report, database, None)))
            except ReportWriteError as exc:
                self.events.put(("import", (exc.report, Path(exc.report.database), str(exc))))
            except Exception as exc:
                self.events.put(("error", str(exc)))
        threading.Thread(target=work, name="chat-import", daemon=False).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'export':
                    self.status.set(f"可读导出完成：{value['conversations']} 个会话、{value['messages']} 条文本。")
                    self.set_result(f"离线可读文件已保存\n\n会话：{value['conversations']}\n文本消息：{value['messages']}\n目录：{value['directory']}\n\n双击 index.html 可查看会话列表；各会话同时有 TXT 文件。\n无需运行微信或聊天浏览服务。\n原归档库未修改。")
                elif kind=="payload":
                    summary=value['summary']
                    self.last_database=None
                    self.last_report=Path(value['report_paths']['summary.md'])
                    if value['status'] in {'success','partial'}: self.blocked_source=self.source.get()
                    self.status.set({'success':'元信息与载荷探测完成','partial':'探测完成，部分采样受限','failed':'载荷探测未完成'}[value['status']])
                    text=(f"{self.status.get()}\n\n元信息文件：{summary['metadata_files']}\n"
                          f"wire 投影兼容：{summary['metadata_wire_compatible']}（字段含义未确认）\n"
                          f"模式覆盖：{summary['patterns_sampled']}/{summary['patterns_total']}\n"
                          f"消息包样本：{summary['chat_samples']}\n索引候选样本：{summary['index_samples']}\n"
                          f"完整样本：{summary['complete_samples']}\n受上限截取：{summary['truncated_samples']}\n"
                          f"正文及元信息读取：{summary['payload_metadata_bytes_read']} 字节\n"
                          f"登记编码流解码：{summary['decoded_streams']}\n\n{value['assessment']['conclusion']}\n"
                          "没有确认真实消息 Schema；本次未写入归档库。\n\n报告：\n")
                    text+='\n'.join(f'{name}：{path}' for name,path in value['report_paths'].items())
                    if value['issues']: text+='\n\n问题：\n'+'\n'.join(i['message'] for i in value['issues'][:30])
                    self.set_result(text)
                elif kind == "analysis":
                    summary = value['summary']
                    if value['scope_kind'] in {'wechat-rmfh-backup', 'rmfh-file'}:
                        self.blocked_source = self.source.get()
                    self.last_database = None
                    self.last_report = Path(value['report_paths']['summary.md'])
                    status = {'success':'RMFH 外壳分析完成', 'partial':'分析完成，部分文件格式未知或损坏',
                              'unsupported':'未识别支持的备份结构', 'failed':'分析未完成'}[value['status']]
                    self.status.set(status)
                    text = (f"{status}\n\n目录：{summary['directories']}\n会话目录候选：{summary['session_directories']}\n"
                            f"文件：{summary['files']}\n总大小：{summary['bytes']/1_000_000_000:.2f} GB\n"
                            f"文件头模式：{len(summary['header_patterns'])} 种\n\n")
                    for category, row in summary['categories'].items():
                        text += (f"{category}：{row['files']} 个文件，{row['rmfh']} 个 RMFH，"
                                 f"{row['supported_envelopes']} 个外壳通过，{row['rejected_envelopes']} 个外壳拒绝\n")
                    text += "\n本次仅分析目录、文件头和外壳区间，未处理聊天正文。\n\n报告：\n"
                    text += "\n".join(f"{name}：{path}" for name,path in value['report_paths'].items())
                    if value['issues']:
                        text += "\n\n问题：\n" + "\n".join(row['message'] for row in value['issues'][:30])
                    self.set_result(text)
                elif kind == "preview":
                    if value.get("kind") == "backup":
                        backup = value["backup_inspection"]
                        self.blocked_source = self.source.get()
                        self.last_database = None
                        self.last_report = Path(backup["report_path"]) if backup["report_path"] else None
                        recognized = backup["inspection_status"] == "recognized"
                        self.status.set("备份结构已识别，聊天正文尚不可导入。" if recognized else "备份结构未通过检查，无法导入。")
                        self.set_result(backup_result_text(backup, value['database'], backup['report_path']))
                        self.set_busy(False)
                        continue
                    issues = value["issues"]
                    self.status.set("预览完成：发现错误，可查看下方详情。" if issues else "预览通过，可以开始导入。")
                    text = f"预览检查（尚未写入数据库）\n\n用户：{value['users']}\n会话：{value['chats']}\n消息：{value['messages']}\n错误：{len(issues)}\n未支持记录跳过：{value['skipped']}\n来源原记录保留：{value.get('retained', 0)}\n目标：{value['database']}\n"
                    if issues:
                        text += "\n问题详情：\n" + "\n".join(issues[:100])
                    self.set_result(text)
                elif kind == "import":
                    report, database, log_error = value
                    status = {"success":"导入完成", "partial":"部分导入完成", "failed":"导入失败"}[report.status]
                    backup = report.source_metadata.get("backup_inspection")
                    if backup:
                        self.blocked_source = self.source.get()
                        status = "备份正文尚不可导入" if backup["inspection_status"] == "recognized" else "备份结构未通过检查"
                    self.status.set(status if not log_error else "导入结果已返回，但报告保存失败，请查看详情。")
                    skipped = report.source_metadata.get("metadata", {}).get("parse_report", {}).get("skipped_unsupported_count", 0)
                    retained = report.source_metadata.get("metadata", {}).get("external_parse", {}).get("quarantined_count", 0)
                    text = f"{status}\n\n新增消息：{report.success_count}\n重复跳过：{report.duplicated_count}\n失败消息：{report.failed_count}\n新增用户：{report.users_created_count}\n复用用户：{report.users_reused_count}\n未支持记录跳过：{skipped}\n来源原记录保留：{retained}\n用时：{report.duration_seconds:.3f} 秒\n归档库：{database}\n报告：{report.report_path or '未保存'}\n"
                    if backup:
                        text = backup_result_text(backup, database, report.report_path or '未保存')
                    if report.issues:
                        text += "\n问题详情：\n" + "\n".join(issue.message for issue in report.issues[:100])
                    if report.warnings:
                        text += "\n\n提示：\n" + "\n".join(issue.message for issue in report.warnings[:30])
                    if log_error:
                        text += "\n\n" + log_error
                    self.set_result(text)
                    self.last_database = database if report.status in {"success", "partial"} and database.is_file() else None
                    self.last_report = Path(report.report_path) if report.report_path else None
                else:
                    self.status.set("未能完成，请检查来源和目标。")
                    self.set_result(value)
                self.set_busy(False)
        except queue.Empty:
            pass
        self.poll_job = self.root.after(80, self.poll)

    def open_browser(self):
        if not self.last_database or self.busy:
            return
        try:
            key = str(self.last_database)
            if key not in self.servers:
                server = make_server(self.last_database, port=0)
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval":0.2}, daemon=True)
                thread.start()
                self.servers[key] = server
            webbrowser.open(self.servers[key].url)
            self.status.set("已打开聊天浏览器；请保留导入窗口，关闭它会停止这里启动的浏览服务。")
        except Exception as exc:
            messagebox.showerror("无法打开聊天", str(exc), parent=self.root)

    def open_report(self):
        if self.last_report and self.last_report.is_file():
            try:
                if hasattr(os, "startfile"):
                    os.startfile(str(self.last_report))
                else:
                    webbrowser.open(self.last_report.as_uri())
            except OSError as exc:
                messagebox.showerror("无法打开报告", str(exc), parent=self.root)

    def close(self):
        if self.busy:
            self.status.set("正在处理数据，请等完成后再关闭窗口。")
            return
        for server in self.servers.values():
            server.shutdown()
            server.server_close()
        self.servers.clear()
        self.root.after_cancel(self.poll_job)
        self.root.update_idletasks()
        self.root.destroy()


def main():
    root = tk.Tk()
    ImportWindow(root)
    root.update_idletasks()
    print(f"Import window ready: {__version__}", flush=True)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
