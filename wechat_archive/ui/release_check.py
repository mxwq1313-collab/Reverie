"""明确调用的 Windows 发布检查；仅创建独立的自建归档。"""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import time

from .. import __version__,ChatService
from ..errors import ConflictError
from ..exporter.readable import _local_path
from .application_controller import ApplicationController
from .application_window import ApplicationWindow


def test_controller(folder):
    folder=_local_path(folder)
    if folder.exists():raise ConflictError('工作台验收目录必须是新目录。')
    folder.mkdir(parents=True);database=folder/'unit_archive.db';service=ChatService(database)
    for identity,name in (('unit_owner','测试自己'),('unit_peer','测试会话 · 独立自建归档'),('unit_second','第二个测试会话')):service.create_user(wxid=identity,nickname=name)
    stamp=datetime(2026,10,10,0,0,tzinfo=timezone.utc)
    texts=('界面验收：这条记录由程序自建，不含个人聊天。','收到。原始文字、时间和方向都应保留。','  原文空格  \n多行 English https://example.invalid\n\n末行  ','关键词：论文修改。请核对上下文。')
    for index in range(125):service.create_message(sender_id=1 if index%2 else 2,receiver_id=2 if index%2 else 1,
        content=texts[index] if index<4 else f'独立自建记录 {index+1}：分页与阅读位置验证。',create_time=stamp+timedelta(minutes=40*index))
    service.create_message(sender_id=3,receiver_id=1,content='第二会话：论文修改。',create_time=stamp-timedelta(days=1))
    def no_source(*args,**options):raise ConflictError('此验收窗口仅使用自建数据，不读取个人微信。')
    controller=ApplicationController(folder/'profile',source_runner=no_source);controller.open_archive(database)
    return controller


def workbench_check(folder,preview=False):
    controller=test_controller(folder);folder=_local_path(folder);before=hashlib.sha256(controller.database.read_bytes()).hexdigest()
    root=tk.Tk();app=ApplicationWindow(root,controller=controller)
    if preview:
        root.title(f'工作台发布验收 · 自建归档 · {__version__}')
        root.mainloop();return None
    root.attributes('-alpha',0)
    try:
        root.update();app.owner_id=1;app.owner_box.current(0);app.peer_id=2;app.load_contacts();root.update()
        assert app.current_page=='聊天归档' and len(app.message_rows)==100 and app.message_total==125
        def settle_layout():
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                root.update()
                view=app.chat_text
                if not app.layout_job and not view.layout_job and not getattr(view,'reflow_busy',False) and not getattr(view,'restore_job',None):return
                time.sleep(.005)
            raise AssertionError('Layout did not settle')
        settle_layout()
        y=app.chat_text.canvas; y.yview_moveto(.1);root.update();position=y.canvasy(0)
        app.load_messages(more=True);settle_layout();assert len(app.message_rows)==125 and abs(y.canvasy(0)-position)<5, {'loaded':len(app.message_rows),'before':position,'after':y.canvasy(0)}
        app.search_scope.set('全部会话');app.search_word.set('论文修改');app.load_messages();root.update();assert app.message_total==2
        app.show_context(126);root.update();assert app.peer_id==3 and app.message_rows[0]['id']==126
        app.peer_id=2;app.load_contacts();app.search_word.set('English');app.load_messages();root.update()
        raw=app.message_rows[0]['content'];app.chat_text.copy_raw(raw);assert root.clipboard_get()==raw
        single=controller.export(folder,1,2);all_archive=controller.export(folder)
        assert single['messages']==125 and all_archive['messages']==126
        routes={}
        for name in (*app.PAGE_NAMES,*app.LEGACY_NAMES):app.show_page(name);root.update();routes[name]=app.current_page
        assert hashlib.sha256(controller.database.read_bytes()).hexdigest()==before
        resources={'ui_modules':True,'primary_pages':list(app.PAGE_NAMES),'legacy_routes':routes}
        experience=client_experience_probe(app,folder,single)
        copilot=copilot_probe(app)
        settings=user_settings_probe(app,folder)
        fast_help=fast_help_probe(app)
        controls=codex_controls_probe(app)
        assert hashlib.sha256(controller.database.read_bytes()).hexdigest()==before
        result={'status':'passed','version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
                'startup':'聊天归档','initial_loaded':100,'conversation_total':125,'loaded_more':125,'reading_position_preserved':True,
                'global_matches':2,'context_target':126,'copy_original_preserved':True,'conversation_export':125,'all_export':126,
                'archive_sha256_unchanged':True,'resources':resources,'client_experience':experience,'copilot_phase1':copilot,'user_settings':settings,'fast_help':fast_help,'codex_controls':controls,'personal_source_read':False,'auth_or_model_request':False}
        (folder/'workbench_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    finally:app.close()


def codex_controls_probe(app):
    root=app.root;panel=app.agent_panel
    app.open_copilot(False);app.show_page('聊天归档');root.update()
    assert app.copilot_button.winfo_ismapped() and app.copilot_hide_button.winfo_ismapped()
    from .icon_button import IconButton
    assert isinstance(panel.copy_button,IconButton) and isinstance(panel.settings_button,IconButton)
    panel.scope_button.invoke();root.update();assert panel.scope_popup.winfo_exists();panel.scope_popup.destroy()
    models=[{'model':'unit-primary','displayName':'Probe model','isDefault':True,'defaultReasoningEffort':'medium','supportedReasoningEfforts':[{'reasoningEffort':'medium'},{'reasoningEffort':'ultra'}]},
            {'model':'unit-hidden','displayName':'Hidden probe','hidden':True,'supportedReasoningEfforts':[{'reasoningEffort':'low'}]}]
    saved=app.controller.settings();panel.set_catalog(models);panel.effort.set('渡劫');panel.fast_mode.set(True)
    assert 'unit-hidden' in panel.model_ids.values() and panel.selected_effort()=='ultra'
    panel.flush_configuration();assert app.controller.settings()['ai']['fast_mode'] is True
    app.controller.save_settings(saved)
    app.show_page('电脑微信');root.update();assert not app.source_tree.winfo_ismapped() and not app.source_cards.winfo_ismapped()
    assert app.detect_button.winfo_ismapped()
    assert [x for x in app.PAGE_NAMES if app.pages[x].winfo_ismapped()]==['添加记录']
    return {'single_collapse_entry':True,'scope_picker':True,'vector_icon_actions':True,'catalog_effort_fast_controls':True,'ordered_add_flow':True,'hidden_pages_unmapped':True}


def fast_help_probe(app):
    saved=app.controller.user_preferences();root=app.root
    for label,mode in (('暖砂','sand'),('雾蓝','blue'),('松绿','green'),('紫雾','violet')):
        app.theme_choice.set(label);app.apply_user_settings();root.update()
        assert app.theme.active_mode==mode
        assert app.controller.user_preferences()['theme']==mode
    app.show_page('帮助');root.update();reader=app.help_reader
    assert app.nav_buttons['帮助'].cget('text')=='Help'
    reader.query.set('Ctrl+L');assert len(reader.visible)==1 and reader.text.tag_ranges('match')
    app.show_page('聊天归档');root.update()
    old=next(iter(app.chat_text.bubbles.values()))['text'];app.load_messages();root.update()
    assert next(iter(app.chat_text.bubbles.values()))['text'] is old
    app.controller.save_user_preferences(saved)
    return {'color_themes_live_persisted':True,'help_search_in_shipped_runtime':True,'english_help':True,'message_widget_reuse':True}


def user_settings_probe(app,folder):
    """Test the shipped preference controls using only this synthetic archive."""
    root=app.root;controller=app.controller;database=controller.database
    original=hashlib.sha256(database.read_bytes()).hexdigest();profile=controller.profile_dir
    settings=controller.user_preferences();panel=app.agent_panel
    ancestor=panel.connect_button;parents=[]
    while ancestor is not None:parents.append(ancestor);ancestor=getattr(ancestor,'master',None)
    assert app.settings_ai_codex in parents and app.copilot_body not in parents
    assert not app.progress.winfo_ismapped()
    app.theme_choice.set('深色');app.language_choice.set('English');app.text_size.set(17)
    app.storage_root.set(str(folder/'future_files'));app.default_export_folder.set(str(folder/'future_exports'))
    app.apply_user_settings();root.update()
    assert app.theme.active_mode=='dark' and app.theme.text_size==17
    assert root.title()=='Sixu' and app.search_scope.get() in ('当前会话','全部会话')
    assert controller.database==database and controller.profile_dir==profile and controller.data_dir==folder/'future_files'
    restored=ApplicationController(profile)
    assert restored.user_preferences()['language']=='en_US' and restored.user_preferences()['theme']=='dark'
    assert hashlib.sha256(database.read_bytes()).hexdigest()==original
    controller.save_user_preferences(settings)
    return {'ai_config_in_settings':True,'dark_theme_live':True,'english_ui_canonical_selectors':True,
            'font_size_live':True,'storage_redirect_without_archive_move':True,'settings_persisted':True,'idle_progress_hidden':True,'archive_sha256_unchanged':True}


def client_experience_probe(app,folder,exported):
    """Exercise the six UI units inside the actual runtime using only test_controller data."""
    controller=app.controller;root=app.root;result={}
    def wait(condition):
        deadline=time.monotonic()+8
        while not condition() and time.monotonic()<deadline:root.update();time.sleep(.01)
        root.update();assert condition(),'Client probe timed out: '+app.knowledge_panel.state.get()+f' [busy={app.knowledge_panel.busy}, running={app.knowledge_panel.running}, hits={len(app.knowledge_panel.hits)}, retry_enabled={not app.knowledge_panel.sync_retry_button.instate(["disabled"])}]'
    assert '基础归档' in app.source_capability_text.get()
    original=controller.database
    controller.upgrade_copy(folder/'unit_extended.db');app.refresh_archive()
    assert '扩展归档' in app.source_capability_text.get()
    controller.open_archive(original);app.refresh_archive()
    result['dynamic_capabilities']=True
    app.owner_id=1;app.owner_box.current(0);app.peer_id=2;app.load_contacts()
    app.search_scope.set('全部会话');app.search_word.set('论文修改');app.load_messages()
    app.show_context(126);app.return_results_button.invoke()
    assert app.message_total==2 and app.search_word.get()=='论文修改' and app.search_scope.get()=='全部会话'
    result['search_round_trip']=True
    app.clear_filters();app.search_scope.set('当前会话');app.peer_id=2;app.load_contacts();root.update()
    panel=app.agent_panel;old_transcript=panel.transcript
    window=tk.Toplevel(root);window.geometry('640x320+0+0');window.attributes('-alpha',0)
    try:
        panel.transcript=ScrolledText(window,wrap='word',font=app.theme.body);panel.transcript.pack(fill='both',expand=True)
        panel.transcript.configure(yscrollcommand=panel.transcript_scrolled)
        panel._add('Codex','\n'.join(f'运行验收行 {i}' for i in range(200)),'unit_stream');root.update()
        panel.transcript.yview_moveto(.2);root.update();top=panel.transcript.index('@0,0')
        panel.transcript.tag_add('sel','45.0','45.end');selection=panel.transcript.get('sel.first','sel.last')
        panel._notification('item/agentMessage/delta',{'itemId':'unit_stream','delta':'\n运行验收增量'})
        assert panel.transcript.index('@0,0')==top and panel.transcript.get('sel.first','sel.last')==selection
        panel.latest_button.invoke();root.update();assert panel.transcript.yview()[1]>.995
        result['streaming_reader_and_selection']=True
    finally:
        panel.transcript=old_transcript;panel._clear();window.destroy()
    panel.pending_request={'question':'开发包自建失败问题','scope':panel.current_scope().key,
        'token':controller.archive_view_token(),'model':panel.model.get()}
    panel._add('Codex','开发包自建部分回答')
    panel._notification('turn/completed',{'turn':{'status':'failed','error':{'message':'synthetic failure'}}})
    panel.edit_failed_question()
    assert panel.input.get('1.0','end').strip()=='开发包自建失败问题'
    assert '开发包自建部分回答' in panel.transcript.get('1.0','end')
    knowledge=app.knowledge_panel;wait(lambda:knowledge.context()==knowledge.last_context)
    knowledge.input.insert('1.0','关键词：论文修改');knowledge.search();wait(lambda:not knowledge.busy)
    assert knowledge.failed_request is not None
    knowledge.sync_retry_button.invoke();wait(lambda:not knowledge.busy and bool(knowledge.hits))
    result['question_recovery_and_index_retry']=True
    app.last_export=exported;app.update_export_actions();launched=[];launch=app.launch_export_path
    try:
        app.launch_export_path=lambda path:launched.append(path)
        app.open_export_button.invoke();app.open_export_folder_button.invoke();app.copy_export_path_button.invoke()
        assert launched==[Path(exported['index']),Path(exported['directory'])]
        assert root.clipboard_get()==exported['directory']
    finally:app.launch_export_path=launch
    result['export_result_actions']=True
    assert all(root.bind(key) for key in ('<Control-f>','<Control-Shift-F>','<Escape>','<Alt-Left>'))
    app.contact_tree.selection_set('2');app.contact_tree.move_selected(1);app.contact_tree.activate_selected()
    assert app.peer_id==3 and app.message_rows[0]['id']==126
    result['keyboard_navigation_bindings']=True
    return result


def copilot_probe(app):
    """Real packaged sidebar and context service; no login, model or personal archive."""
    root=app.root;panel=app.agent_panel
    assert panel.compact and panel.client is None
    for page in app.PAGE_NAMES:
        app.show_page(page);root.update();assert app.copilot_host.winfo_ismapped()
    app.show_page('聊天归档');app.copilot_button.invoke() if not app.copilot_expanded else app.open_copilot();root.update()
    scope=panel.current_scope();request=panel.ai_service.prepare('开发包自建上下文提问',scope)
    payload=request.context.to_payload()
    assert (payload['user_id'],payload['peer_id'])==(app.owner_id,app.peer_id)
    assert payload['conversation_id']==f'private:{app.owner_id}:{app.peer_id}'
    assert request.context.scope_key==scope.key and 'source_token' not in payload
    assert payload['visible_messages']==[] and payload['selected_messages']==[]
    assert 'evidence' in payload['metadata'] and root.bind('<Control-l>')
    app.hide_copilot();assert not app.copilot_expanded
    app.copilot_shortcut();root.update();assert app.copilot_expanded and panel.client is None
    assert app.controller.copilot_layout()['expanded']
    return {'resident_all_pages':True,'single_panel':True,'collapsed_and_restored':True,
        'context_bound':True,'bounded_metadata_only':True,'service_loaded':True,
        'ctrl_l_route':True,'personal_source_read':False,'model_request':False}
