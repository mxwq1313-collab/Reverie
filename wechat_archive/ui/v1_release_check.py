"""Frozen 1.0 runtime probe. All data is created here; no personal sources or model."""
import json
from pathlib import Path
import sqlite3
import sys
import tkinter as tk
from PIL import Image
from .. import __version__
from ..importer.rich_importer import create_rich_archive,RichImporter,sha_file
from .application_controller import ApplicationController
from .application_window import ApplicationWindow


def v1_check(folder):
    folder=Path(folder).resolve()
    if folder.exists():raise ValueError('验证目录必须为新目录')
    folder.mkdir(parents=True);database=folder/'synthetic.db';create_rich_archive(database)
    frames=[Image.new('RGB',(96,72),color) for color in ('#518867','#9cba96')]
    frames[0].save(folder/'picture.gif',save_all=True,append_images=frames[1:],duration=100,loop=0);(folder/'binary.bin').write_bytes(bytes(range(256))*8)
    payload={'format':'sixu-chat-exchange','format_version':'2.0','namespace':'synthetic-release-v1','users':[{'id':'release_self','nickname':'自己'},{'id':'release_peer','nickname':'伙伴'}],
        'chats':[{'id':'group','kind':'group','title':'合成群聊','members':['release_self','release_peer']},{'id':'private','kind':'private','title':'私聊','members':['release_self','release_peer']}],
        'messages':[{'id':'g1','chat_id':'group','sender_id':'release_self','kind':'text','content':'群内原文 😀','create_time':'2026-10-15T00:00:00Z'},
                    {'id':'g2','chat_id':'group','sender_id':'release_peer','kind':'emoji','content':'[表情]','create_time':'2026-10-15T00:01:00Z','attachments':[{'kind':'image','path':'picture.gif'}]},
                    {'id':'g3','chat_id':'group','sender_id':'release_peer','kind':'file','content':'文件','create_time':'2026-10-15T00:02:00Z','attachments':[{'kind':'file','path':'binary.bin'}]},
                    {'id':'p1','chat_id':'private','sender_id':'release_self','receiver_id':'release_peer','kind':'text','content':'私聊原文','create_time':'2026-10-15T00:03:00Z'}]}
    source=folder/'input.json';source.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8');importer=RichImporter(database);first=importer.import_file(source);repeat=importer.import_file(source)
    assert (first.success_count,repeat.duplicated_count)==(4,4)
    controller=ApplicationController(folder/'profile');controller.open_archive(database);group=next(x for x in controller.contacts(1) if x['kind']=='group')
    assert (group['message_count'],group['own_count'])==(3,1)
    before=sha_file(database);root=tk.Tk();root.geometry('1400x860');errors=[];root.report_callback_exception=lambda *x:errors.append(str(x));app=ApplicationWindow(root,controller=controller)
    try:
        root.update();app.owner_id=1;app.peer_id=group['id'];app.load_contacts();root.update();assert len(app.message_rows)==3
        assert any(hasattr(w,'attachment_item') for w in app.descendants(app.chat_text))
        assert not any(w.winfo_class()=='TButton' and w.cget('text')=='另存附件' for w in app.descendants(app.chat_text))
        from .media_widgets import preview_image
        animated=preview_image(app,app.message_rows[1]['attachments'][0]);root.after(160,root.quit);root.mainloop()
        play=next(w for w in app.descendants(animated) if w.winfo_class()=='TButton' and w.cget('text')=='播放 / 暂停');play.invoke();root.after(180,root.quit);root.mainloop()
        root.tk.call(animated.protocol('WM_DELETE_WINDOW'))
        panel=app.agent_panel;assert panel.history_button.winfo_ismapped();panel.parameters_button.invoke();root.update();assert panel.power_model_button.winfo_ismapped() and panel.power_slider.winfo_ismapped();panel.parameters_popup.withdraw()
        panel.history_store.save({'title':'合成历史','messages':[{'role':'你','text':'问题'},{'role':'Codex · 回答','text':'合成回答'}],'scope':[str(database),1,2],'archive_name':database.name})
        assert len(panel.history_store.list())==1;panel.show_history();root.update()
        app.show_page('帮助');root.update();app.help_reader.query.set('附件');root.update();assert app.help_reader.visible
        controller.source_runner=lambda *a,**k:{'owner':{'nickname':'自建账号'},'contacts':[{'username':'synthetic_group@chatroom','name':'合成群聊','kind':'group','message_count':3,'own_count':1,'own_ratio':1/3,'members':[{'username':'release_peer','name':'伙伴','message_count':2,'ratio':2/3}]}]}
        app.accounts=[{'account':'synthetic','wxid':'release_self'}];app.account_box.configure(values=('自建账号',));app.account_box.current(0);app.source_root.set(str(folder));app.show_page('电脑微信');app.load_source_contacts()
        import time
        deadline=time.monotonic()+10
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        root.update();assert app.source_tree.get_children('0');assert not app.source_tree.item('0','open');assert app.source_tree.winfo_ismapped()
        exported=controller.export(folder/'export',1,group['id']);assert exported['messages']==3
        copies=list(Path(exported['directory']).rglob('*.bin'));assert len(copies)==1 and copies[0].read_bytes()==(folder/'binary.bin').read_bytes()
        assert sha_file(database)==before;assert not errors,errors
        receipt={'status':'passed','version':__version__,'frozen':bool(getattr(sys,'frozen',False)),'groups_and_members':True,'own_ratio':group['own_ratio'],'unicode_emoji':True,'animated_gif_preview':True,'image_preview_and_file_save':True,'binary_export_unchanged':True,'history_ui_and_persistence':True,'combined_model_effort':True,'folded_source_groups':True,'help_search':True,'archive_sha256_unchanged':True,'personal_source_read':False,'real_inference':False}
        from .v11_release_check import verify_v11
        receipt['sixu_1_1']=verify_v11(app,folder)
        from .large_release_check import verify_large_ui
        receipt['large_archive_ui']=verify_large_ui(app)
        from .v2_release_check import verify_v2
        receipt['sixu_2_0']=verify_v2(app,folder)
        (folder/'sixu_v1_check.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8');return receipt
    finally:app.close()
