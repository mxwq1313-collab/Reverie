"""既有获取、导入、导出和数据管理操作；继续调用原控制器。"""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import os
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
from tkinter.scrolledtext import ScrolledText
from uuid import uuid4
from ..errors import ValidationError
from .import_controller import FORMAT_LABELS


class OperationActions:
    def choose_source_root(self):
        value=filedialog.askdirectory(parent=self.root,title='选择电脑微信数据目录')
        if value:self.source_root.set(value)

    def detect_source(self):
        root=self.source_root.get().strip() or None
        def done(result):
            self.source_root.set(result['root']);self.accounts=result['accounts'];self.update_account_labels()
            labels=self.account_box.cget('values')
            if labels:self.account_box.current(0)
            self.source_info.set(f"检测到 {len(labels)} 个账号 · 电脑微信 {result['client_version']}，请选择账号并连接。");self.status.set('账号检测完成。');self.source_step.set('2 · 选择账号并连接')
        self.run('正在检测电脑微信账号…',lambda:self.controller.discover(root),done)

    def update_account_labels(self):
        from .account_labels import account_labels
        selected=self.account_box.current();self.account_box.configure(values=account_labels(self.accounts))
        if 0<=selected<len(self.accounts):self.account_box.current(selected)

    def account_selection(self):
        index=self.account_box.current()
        if index<0:raise ValidationError('请先检测并选择账号。')
        return self.source_root.get().strip(),self.accounts[index]['account']

    def source_account_changed(self):
        self.source_peers=[]
        if hasattr(self,'source_renderer'):self.source_renderer.cancel()
        children=self.source_tree.get_children()
        if children:self.source_tree.delete(*children)
        self.refresh_source_selection()
        self.source_info.set('账号已切换，请连接并加载此账号的联系人。')

    def load_source_contacts(self):
        try:root,account=self.account_selection()
        except Exception as error:self.status.set(str(error));return
        keyword=self.source_keyword.get().strip() or None
        def done(result):
            owner=result['owner']
            for value in self.accounts:
                if value['account']==account and value.get('wxid')==owner.get('wxid'):
                    value.update(nickname=owner['nickname'],weixin_id=owner.get('weixin_id') or value.get('weixin_id',''),identity_status='verified')
            self.update_account_labels()
            self.source_peers=[row for row in result['contacts'] if row.get('message_count',0)>0]
            from .source_tree import SourceTreeRenderer
            if not hasattr(self,'source_renderer'):self.source_renderer=SourceTreeRenderer(self)
            self.source_renderer.set_rows(self.source_peers)
            self.refresh_source_selection()
            self.source_info.set(f"已连接 {result['owner']['nickname']} · {len(self.source_peers)} 个会话候选；选择联系人或群名。");self.status.set('联系人读取完成。');self.source_step.set('3 · 选择联系人与读取范围')
        self.run('正在只读连接并核验账号，加载联系人…',lambda:self.controller.source_contacts(root,account,keyword,rich=True),done)

    def update_wechat_avatars(self):
        if self.owner_id is None:self.status.set('请先选择微信本人身份。');return
        owner=self.owner_id;database=self.controller.database
        root=self.source_root.get().strip() or None
        def done(result):
            if database==self.controller.database and owner==self.owner_id:self.load_contacts()
            self.status.set(f"头像已更新：{result['ready']} 个；{result['missing']} 个在微信本地没有缓存。")
        self.run('正在读取微信本地头像…',lambda:self.controller.sync_avatars(owner,root),done)

    def acquire_source(self):
        try:
            root,account=self.account_selection();selection=self.source_tree.selection()
            if not selection or selection[0].startswith('member:'):raise ValidationError('请选择联系人或群名；成员行显示群内发言统计。')
            peer=self.source_peers[int(selection[0])]['username'];self.ensure_archive()
            if not self.source_peers[int(selection[0])].get('message_count'):raise ValidationError('所选会话没有消息，无需读取。')
        except Exception as error:self.status.set(str(error));return
        from .source_options import selected_range
        try:all_history,limit=selected_range(self.source_scope.get())
        except ValidationError as error:self.status.set(str(error));return
        allow_cdn=self.source_allow_cdn.get()
        def done(result):
            report=result['report'];self.source_cards.show_report(report);self.source_step.set('4 · 查看归档结果');self.write(self.source_result,self.report_summary(report)+f"\n来源记录：{result['capture']['records']}\n原始来源保存在：{result['capture']['output']}");self.refresh_archive();capture=result['capture'];self.write(self.source_result,f"\n附件：取得 {capture.get('media_available',0)} / {capture.get('attachments',0)}；未取得 {capture.get('media_missing',0)}；处理异常 {capture.get('media_failures',0)}。缺失的本地缓存可在微信中查看后重新读取。",append=True);self.status.set('微信读取与归档完成。' if report.status in {'success','partial'} else '来源已读取，但导入失败，请查看下方原因。')
            statuses=capture.get('media_status_counts',{});self.write(self.source_result,'\n媒体诊断：'+json.dumps(statuses,ensure_ascii=False),append=True)
            if capture.get('media_missing',0):
                self.source_cards.state.set('记录已归档，部分附件未取得；请查看详细原因。');self.source_cards.expander.set_expanded(True);self.status.set('部分附件未取得，请查看媒体诊断。')
        self.run('正在只读获取所选会话，并导入归档…',lambda:self.controller.acquire_import(root,account,peer,limit,all_history,rich=True,allow_cdn=allow_cdn),done)

    def repair_archived_emojis(self):
        if not self.controller.database:self.status.set('请先打开需要补全表情的归档。');return
        allow_cdn=self.source_allow_cdn.get()
        def done(result):
            self.refresh_archive();self.write(self.source_result,f"表情检查完成：检查 {result['checked']} 条，补全 {result['repaired']} 条，已有 {result['ready']} 条，未取得 {result['missing']} 条。"+('\n已取消，已补全的附件保留。' if result['cancelled'] else ''))
            self.source_info.set(f"表情检查：补全 {result['repaired']} 条；已有 {result['ready']} 条；未取得 {result['missing']} 条。"+('已取消，已补全的附件保留。' if result['cancelled'] else ''))
            self.status.set('表情补全完成。' if not result['missing'] else '部分表情资源未取得；可在微信打开表情后重新读取。')
        self.run('正在补全微信归档表情…',lambda:self.controller.repair_emojis(allow_cdn),done)

    def import_copy_file(self):
        path=filedialog.askopenfilename(parent=self.root,title='导入副本文件',filetypes=[('归档或聊天副本','*.db *.sqlite *.sqlite3 *.json *.csv'),('全部文件','*.*')])
        if not path:return
        self.import_source.set(path);self.import_kind.set(FORMAT_LABELS['auto']);self.show_page('导入文件');self.import_action(False)

    def pick_import_file(self):
        path=filedialog.askopenfilename(parent=self.root,title='选择来源文件',filetypes=[('聊天文件','*.json *.csv *.db *.sqlite *.sqlite3'),('全部文件','*.*')])
        if path:self.import_source.set(path)
    def pick_import_folder(self):
        path=filedialog.askdirectory(parent=self.root,title='选择来源目录')
        if path:self.import_source.set(path)

    def import_action(self,preview):
        source=self.import_source.get().strip();chosen=next(key for key,value in FORMAT_LABELS.items() if value==self.import_kind.get());strict=self.import_strict.get();namespace=self.csv_namespace.get();zone=self.csv_zone.get()
        if not source:self.status.set('请先选择来源文件或目录。');return
        if not preview and self.controller.is_archive_copy(source):
            def copied(result):
                self.refresh_archive();self.show_page('聊天归档');self.status.set('副本已导入并打开。')
            self.run('正在导入归档副本…',lambda:self.controller.import_archive_copy(source),copied);return
        if not preview:
            try:self.ensure_archive()
            except Exception as error:self.status.set(str(error));return
        target=self.controller.database or self.controller.data_dir/'chat.db'
        def done(result):
            if preview:self.import_cards.show_preview(result);self.import_step.set('2 · 预览检查完成');self.write(self.import_result,json.dumps(result,ensure_ascii=False,indent=2));self.status.set('预览完成，尚未写入聊天记录。')
            else:self.import_cards.show_report(result);self.import_step.set('3 · 查看导入结果');self.write(self.import_result,self.report_summary(result));self.refresh_archive();self.status.set('文件导入完成，请查看结果。')
        work=(lambda:self.controller.imports.preview(source,target,chosen,strict=strict,namespace=namespace,timezone=zone)) if preview else (lambda:self.controller.import_file(source,chosen,strict,namespace,zone))
        self.run('正在预览检查…' if preview else '正在导入文件…',work,done)

    def report_summary(self,report):
        retained=report.source_metadata.get('quarantined_count',report.source_metadata.get('metadata',{}).get('external_parse',{}).get('quarantined_count',0))
        text=f"状态：{report.status}\n新增消息：{report.success_count}\n重复跳过：{report.duplicated_count}\n失败消息：{report.failed_count}\n未支持原记录保留：{retained}\n报告：{report.report_path}"
        if report.source_metadata.get('mode')=='streaming-partial-commit':
            text+=f"\n已确认来源记录：{report.source_metadata['processed_records']} / {report.source_metadata['source_records']}\n已提交批次：{report.source_metadata['committed_batches']}；中断后可恢复，原始快照仍保留。"
        if report.source_metadata.get('retained_unmapped_senders'):
            text+=f"\n发送者身份未映射：{report.source_metadata['retained_unmapped_senders']} 条，正文已保留。"
        if report.issues:text+='\n\n问题：\n'+'\n'.join(item.message for item in report.issues[:30])
        if report.warnings:text+='\n\n提示：\n'+'\n'.join(item.message for item in report.warnings[:20])
        return text

    def pick_export_parent(self):
        path=filedialog.askdirectory(parent=self.root,title='选择保存位置')
        if path:self.export_parent.set(path)
    def export_action(self):
        self.last_export=None;self.update_export_actions()
        parent=self.export_parent.get().strip();scope=self.export_scope.get();kind=self.export_format.get();zone=self.export_zone.get();owner=None if scope in ('全部已归档文本','全部已归档内容') else self.owner_id;peer=self.peer_id if scope=='当前会话' else None
        if not parent:self.status.set('请选择保存位置。');return
        if scope not in ('全部已归档文本','全部已归档内容') and owner is None or scope=='当前会话' and peer is None:self.status.set('请先在聊天归档页选择身份和会话。');return
        formats=('html','txt') if kind=='HTML 和 TXT' else ('html',) if kind=='仅 HTML' else ('txt',)
        def done(result):
            self.last_export=dict(result);self.update_export_actions()
            self.write(self.export_result,f"保存完成\n\n会话：{result['conversations']}\n消息：{result['messages']}\n位置：{result['directory']}\n\n使用下方按钮打开结果或复制路径。原归档未修改。");self.status.set('可读导出完成。')
        self.run('正在保存离线可读文件…',lambda:self.controller.export(parent,owner,peer,formats,zone),done)

    def update_export_actions(self):
        if not hasattr(self,'open_export_button'):return
        enabled=self.last_export is not None
        for button in (self.open_export_button,self.open_export_folder_button,self.copy_export_path_button):
            button.configure(state='normal' if enabled else 'disabled')
        if enabled:
            name='打开阅读首页' if self.last_export.get('index') else '打开 TXT 文件' if self.last_export['conversations']==1 else '打开 TXT 文件夹'
            self.open_export_button.configure(text=name)

    def export_result_path(self,folder=False):
        if not self.last_export:raise ValueError('尚无已完成的导出结果。')
        directory=Path(self.last_export['directory']).resolve(strict=True)
        if folder or self.last_export['conversations']!=1 and not self.last_export.get('index'):return directory
        if self.last_export.get('index'):target=Path(self.last_export['index']).resolve(strict=True)
        else:
            targets=list(directory.glob('chat_*.txt'))
            if len(targets)!=1:raise ValueError('TXT结果缺失或已变化，请打开导出文件夹检查。')
            target=targets[0].resolve(strict=True)
        if target.parent!=directory or not target.is_file():raise ValueError('导出阅读文件缺失或已变化。')
        return target

    def launch_export_path(self,path):
        os.startfile(str(path))

    def open_export_result(self,folder=False):
        try:
            target=self.export_result_path(folder);self.launch_export_path(target)
            self.status.set('已请求系统打开导出结果：'+str(target))
        except Exception as error:self.status.set('导出结果未能打开：'+str(error))

    def copy_export_path(self):
        try:
            target=self.export_result_path(True);self.root.clipboard_clear();self.root.clipboard_append(str(target))
            self.status.set('导出目录路径已复制。')
        except Exception as error:self.status.set('路径未复制：'+str(error))

    def user_editor(self,edit=False):
        try:self.controller.require_archive()
        except Exception as error:self.status.set(str(error));return
        selected=self.user_tree.selection();row=next((value for value in self.archive_users if selected and value['id']==int(selected[0])),None) if edit else None
        if edit and row is None:self.status.set('请选择联系人。');return
        from .workspace_widgets import card
        dialog=tk.Toplevel(self.root);dialog.title('编辑联系人' if edit else '新增联系人');dialog.geometry(f'{self.theme.u(580)}x{self.theme.u(410)}');dialog.transient(self.root)
        shell=ttk.Frame(dialog,padding=self.theme.u(20));shell.pack(fill='both',expand=True)
        self.title(shell,'联系人资料','昵称用于显示；来源标识用于区分身份。')
        body=card(shell,self.theme,'基本信息');form=ttk.Frame(body);form.pack(fill='x');form.columnconfigure(1,weight=1)
        nickname=tk.StringVar(dialog,value=row['nickname'] if row else '');identity=tk.StringVar(dialog,value=row['wxid'] if row else 'manual:'+uuid4().hex);avatar=tk.StringVar(dialog,value=(row.get('avatar') or '') if row else '')
        for i,(label,var) in enumerate((('昵称',nickname),('来源标识',identity),('头像路径',avatar))):
            ttk.Label(form,text=label).grid(row=i,column=0,sticky='w',padx=(0,self.theme.u(18)),pady=self.theme.u(7))
            field=ttk.Entry(form,textvariable=var,state='readonly' if edit and var is identity else 'normal');field.grid(row=i,column=1,sticky='ew')
        error_text=tk.StringVar(dialog);ttk.Label(shell,textvariable=error_text,style='Hint.TLabel',wraplength=self.theme.u(500)).pack(fill='x')
        footer=ttk.Frame(shell);footer.pack(side='bottom',fill='x',pady=(self.theme.u(12),0))
        def save():
            try:
                fields={'nickname':nickname.get(),'avatar':avatar.get() or None}
                if not edit:fields['wxid']=identity.get()
                self.controller.manage_user('update' if edit else 'create',row['id'] if row else None,**fields);dialog.destroy();self.refresh_archive();self.status.set('联系人资料已保存。')
                if hasattr(self,'feedback'):self.feedback.show('联系人资料已保存。')
            except Exception as error:error_text.set('未保存：'+str(error))
        self.button(footer,'保存联系人',save,True).pack(side='right');self.button(footer,'取消',dialog.destroy).pack(side='right',padx=self.theme.u(8))
        self.theme.apply_tree(dialog);dialog.grab_set()

    def delete_user(self):
        selected=self.user_tree.selection()
        if not selected:self.status.set('请选择联系人。');return
        if messagebox.askyesno('确认删除','删除当前归档中的所选联系人？有关联消息时会拒绝。',parent=self.root):
            try:self.controller.manage_user('delete',int(selected[0]));self.refresh_archive()
            except Exception as error:messagebox.showerror('未删除',str(error),parent=self.root)

    def message_editor(self,edit=False):
        if not self.archive_users:self.status.set('请先打开归档并添加联系人。');return
        selected=self.message_tree.selection();row=next((value for value in self.message_rows if selected and value['id']==int(selected[0])),None) if edit else None
        if edit and row is None:self.status.set('请选择一条消息。');return
        readonly=bool(row and (row.get('chat_kind')=='group' or row.get('msg_type','text')!='text' or (row.get('attachments') and (row.get('content') or '').lstrip().startswith('<'))))
        dialog=tk.Toplevel(self.root);dialog.title('查看归档消息' if readonly else '编辑归档文本' if edit else '新增归档文本');dialog.geometry(f'{self.theme.u(680)}x{self.theme.u(590)}');dialog.minsize(self.theme.u(520),self.theme.u(440));dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=self.theme.u(22));frame.pack(fill='both',expand=True)
        self.title(frame,'消息详情' if readonly else '编辑归档文本' if edit else '新增归档文本','保留原始会话与附件结构；此窗口只读查看。' if readonly else '整理当前归档中的文本，保存后更新会话视图。')
        form=ttk.Frame(frame);form.pack(fill='x',pady=(self.theme.u(8),self.theme.u(10)));form.columnconfigure(1,weight=1)
        labels=[f"{value['nickname']} · {value['id']}" for value in self.archive_users];ids=[value['id'] for value in self.archive_users]
        sender=tk.StringVar(dialog);receiver=tk.StringVar(dialog)
        for index,(caption,var,initial) in enumerate((('发送者',sender,row['sender_id'] if row else self.owner_id),('接收者',receiver,row['receiver_id'] if row else self.peer_id))):
            ttk.Label(form,text=caption).grid(row=index,column=0,sticky='w',padx=(0,self.theme.u(20)),pady=self.theme.u(7))
            box=ttk.Combobox(form,textvariable=var,values=labels,state='disabled' if readonly else 'readonly');box.grid(row=index,column=1,sticky='ew');box.current(ids.index(initial) if initial in ids else 0)
            if row and initial is None:box.set((row.get('chat_title') or '群聊') if caption=='接收者' and row.get('chat_kind')=='group' else '未映射身份')
        zone=timezone(timedelta(hours=8));original_display=datetime.fromisoformat(row['create_time'].replace('Z','+00:00')).astimezone(zone).strftime('%Y-%m-%d %H:%M:%S') if row else datetime.now(zone).strftime('%Y-%m-%d %H:%M:%S')
        stamp=tk.StringVar(dialog,value=original_display);ttk.Label(form,text='时间 · 北京时间').grid(row=2,column=0,sticky='w',padx=(0,self.theme.u(20)),pady=self.theme.u(7));ttk.Entry(form,textvariable=stamp,state='readonly' if readonly else 'normal').grid(row=2,column=1,sticky='ew')
        ttk.Label(frame,text='消息内容',font=self.theme.name).pack(anchor='w',pady=(self.theme.u(8),self.theme.u(5)))
        content=ScrolledText(frame,height=8,wrap='word',font=self.theme.body);self.theme.text_surface(content,editable=not readonly,framed=True);content.pack(fill='both',expand=True)
        if readonly:
            from .media_widgets import present_content
            content.insert('1.0',present_content(row)+('\n\n请从附件详情查看、播放或另存资源。' if row.get('attachments') else ''));content.configure(state='disabled')
            from .common_widgets import Collapsible
            original=Collapsible(frame,'原始内容（只读）',self.theme);original.pack(fill='x',pady=self.theme.u(8))
            raw=ScrolledText(original.content,height=4,wrap='char',font=('Consolas',-self.theme.u(12)));self.theme.text_surface(raw);raw.pack(fill='x');raw.insert('1.0',row['content'] or '');raw.configure(state='disabled')
        elif row:content.insert('1.0',row['content'])
        error_text=tk.StringVar(dialog);error_label=ttk.Label(frame,textvariable=error_text,style='Hint.TLabel',wraplength=self.theme.u(580));error_label.pack(fill='x',pady=self.theme.u(4))
        footer=ttk.Frame(frame);footer.pack(side='bottom',fill='x',pady=(self.theme.u(8),0),before=content.frame)
        error_label.pack_configure(side='bottom',before=content.frame)
        if readonly:original.pack_configure(side='bottom',before=content.frame)
        dialog.variables=(sender,receiver,stamp,error_text)
        def save():
            try:
                timestamp=row['create_time'] if row and stamp.get()==original_display else datetime.strptime(stamp.get(),'%Y-%m-%d %H:%M:%S').replace(tzinfo=zone).isoformat()
                fields={'sender_id':self.archive_users[labels.index(sender.get())]['id'],'receiver_id':self.archive_users[labels.index(receiver.get())]['id'],'create_time':timestamp,'content':content.get('1.0','end-1c')}
                self.controller.manage_message('update' if edit else 'create',row['id'] if row else None,**fields);dialog.destroy();self.refresh_archive();self.status.set('归档文本已保存。')
                if hasattr(self,'feedback'):self.feedback.show('归档文本已保存。')
            except Exception as error:error_text.set('未保存：'+str(error))
        if readonly:
            items=row.get('attachments',[])
            if items:
                def details():
                    from .media_widgets import attachment_details
                    dialog.destroy();attachment_details(self,items[0],related=items,message=row)
                self.button(footer,'查看附件详情',details,True).pack(side='right')
            self.button(footer,'关闭',dialog.destroy).pack(side='right',padx=self.theme.u(8))
        else:
            self.button(footer,'保存文本',save,True).pack(side='right');self.button(footer,'取消',dialog.destroy).pack(side='right',padx=self.theme.u(8))
        self.theme.apply_tree(dialog);dialog.grab_set()

    def delete_message(self):
        selected=self.message_tree.selection()
        if not selected:self.status.set('请选择一条消息。');return
        if messagebox.askyesno('确认删除','删除当前归档中的所选消息？',parent=self.root):
            try:self.controller.manage_message('delete',int(selected[0]));self.refresh_archive()
            except Exception as error:messagebox.showerror('未删除',str(error),parent=self.root)

    def pick_backup(self):
        path=filedialog.askdirectory(parent=self.root,title='选择备份目录')
        if path:self.backup_source.set(path)
    def backup_action(self,action):
        source=self.backup_source.get().strip()
        if not source:self.status.set('请选择备份目录。');return
        def work():
            if action=='analyze':return self.controller.imports.analyze_backup(source)
            if action=='study':return self.controller.imports.study_payload(source)
            from ..wechat_adapter import BackupAdapter
            report=BackupAdapter().inspect(source);report.save(self.controller.data_dir/'import_logs');return report.to_dict()
        def done(result):self.write(self.backup_result,json.dumps(result,ensure_ascii=False,indent=2));self.refresh_reports();self.status.set('备份检查完成，正文支持状态以报告为准。')
        self.run('正在只读检查备份…',work,done)

    def refresh_reports(self):
        for item in self.report_tree.get_children():self.report_tree.delete(item)
        self.report_paths={}
        for index,path in enumerate(self.controller.report_files()[:300]):self.report_paths[str(index)]=path;self.report_tree.insert('','end',iid=str(index),values=(path.name,datetime.fromtimestamp(path.stat().st_mtime,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')))
    def select_report(self,event=None):
        selected=self.report_tree.selection()
        if selected:
            try:self.write(self.report_text,json.dumps(self.controller.read_report(self.report_paths[selected[0]]),ensure_ascii=False,indent=2))
            except Exception as error:self.status.set(str(error))
    def open_data_folder(self):
        self.controller.data_dir.mkdir(parents=True,exist_ok=True)
        if hasattr(os,'startfile'):os.startfile(str(self.controller.data_dir))

    def upgrade_archive_copy(self):
        try:source=self.controller.require_archive()
        except Exception as error:self.status.set(str(error));return
        target=filedialog.asksaveasfilename(parent=self.root,title='创建新的升级副本，原库保留',defaultextension='.db',initialfile=source.stem+'-升级副本.db',filetypes=[('聊天归档','*.db')])
        if not target:return
        def done(result):
            self.refresh_archive();self.status.set('升级副本已验证并打开；原库保留，全部历史可使用封存分批路径。')
        self.run('正在验证并创建新的升级副本…',lambda:self.controller.upgrade_copy(target),done)

