"""Explicit packaged offline self-check, synthetic data only, no inference."""

import json
from pathlib import Path
import sys
import time
import tkinter as tk

from ..errors import ConflictError
from ..exporter.readable import _local_path
from ..services import ChatService
from ..ui.application_controller import ApplicationController
from ..ui.application_window import ApplicationWindow
from .api import KnowledgeAPI


def knowledge_check(folder):
    folder=_local_path(folder)
    if folder.exists(): raise ConflictError('知识验收目录必须是新目录。')
    folder.mkdir(parents=True)
    service=ChatService(folder/'synthetic.db')
    for i in range(3): service.create_user(wxid=f'release_fixture_{i}',nickname=f'自建身份{i}')
    for peer,text in ((2,'发布知识诊断：晶界偏聚能采用四能量计算。'),(3,'其他会话不得返回')):
        service.create_message(sender_id=1,receiver_id=peer,content=text,create_time='2026-10-14T00:00:00Z')
    root=tk.Tk(); root.withdraw()
    app=ApplicationWindow(root,controller=ApplicationController(folder/'profile'),archive=folder/'synthetic.db')
    def wait(condition):
        deadline=time.monotonic()+15
        while not condition() and time.monotonic()<deadline: root.update(); time.sleep(.01)
        root.update()
        if not condition(): raise ConflictError('知识界面操作超时。')
    try:
        app.owner_id=1; app.peer_id=2; app.load_messages(); app.show_page('本地知识问答')
        panel=app.knowledge_panel
        wait(lambda:panel.context()==panel.last_context)
        panel.sync(); wait(lambda:not panel.busy)
        if '索引已更新' not in panel.state.get(): raise ConflictError(panel.state.get())
        panel.input.insert('1.0','晶界偏聚能'); panel.search(); wait(lambda:not panel.busy)
        if len(panel.hits)!=1: raise ConflictError('知识检索范围或结果不符合预期。')
        panel.tree.selection_set('0'); root.update()
        if '四能量计算' not in panel.output.get('1.0','end'): raise ConflictError('原文回查未显示。')
        source,index=panel.components(); api=KnowledgeAPI(source,index)
        capabilities=api.call('capabilities',{})
        ref=panel.hits[0]['chunk']['reference']
        api.call('resolve',{'reference':ref})
        app.controller.manage_message('update',message_id=1,content='发布知识诊断修改后的原文。')
        wait(lambda:not panel.hits)
        rejected=api.dispatch({'version':'1.0','id':1,'method':'resolve','params':{'reference':ref}})
        if rejected['ok']: raise ConflictError('过期证据未撤销。')
        result={'status':'passed','frozen':bool(getattr(sys,'frozen',False)),'api_version':capabilities['api_version'],
                'methods':capabilities['methods'],'source_messages':1,'hits':1,'readonly_preview':True,
                'scope_isolation':True,'source_change_revoked':True,'model_requested':False,
                'real_chat_read':False,'real_inference':False,'pages':list(app.pages)}
        (folder/'knowledge_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        return result
    finally: app.close()
