"""Frozen v2 contract with a synthetic sticker transport, no real requests."""
from contextlib import closing
import hashlib,json,sqlite3,time,tkinter as tk
from PIL import Image
from .. import __version__
from ..importer.rich_importer import create_rich_archive,RichImporter
from ..wechat_source.emoji_fetch import EmojiFetch
from .application_controller import ApplicationController
from .application_window import ApplicationWindow
from .source_options import selected_range


def verify_v2(parent,folder):
    folder=folder/'v2';folder.mkdir();database=folder/'synthetic.db';create_rich_archive(database)
    poster=folder/'synthetic.gif';Image.new('RGB',(32,28),'green').save(poster,format='GIF');key=hashlib.md5(poster.read_bytes()).hexdigest()
    payload={'format':'sixu-chat-exchange','format_version':'2.0','namespace':'synthetic-release-v2','users':[{'id':'v2_self','nickname':'自己'},{'id':'v2_peer','nickname':'伙伴'}],
             'chats':[{'id':'private','kind':'private','members':['v2_self','v2_peer']}],'messages':[{'id':'emoji','chat_id':'private','sender_id':'v2_peer','receiver_id':'v2_self','kind':'emoji','content':'<msg><emoji md5="'+key+'" cdnurl="https://emoji.qpic.cn/synthetic-resource"/></msg>','create_time':'2026-10-16T00:00:00Z','attachments':[{'kind':'image','path':None,'name':'synthetic sticker'}]}]}
    payload['messages'].append({'id':'inline-emoji','chat_id':'private','sender_id':'v2_peer','receiver_id':'v2_self','kind':'text','content':'文本表情[流泪]与[捂脸]混排','create_time':'2026-10-16T00:01:00Z','attachments':[]})
    source=folder/'input.json';source.write_text(json.dumps(payload),encoding='utf-8');RichImporter(database).import_file(source)
    controller=ApplicationController(folder/'profile');controller.open_archive(database);root=tk.Tk();root.attributes('-alpha',0);root.geometry('1100x760');errors=[];root.report_callback_exception=lambda *args:errors.append(str(args));app=ApplicationWindow(root,controller=controller)
    original=EmojiFetch.acquire
    try:
        root.update();assert __version__=='2.2.1';assert app.source_scope.get()=='全部电脑本地记录';assert selected_range('最近 100 万条')==(False,1000000)
        offline=controller.repair_emojis(False);assert offline['missing']==1
        # Only the resource transport is substituted; repair, commit and Tk decode stay real.
        EmojiFetch.acquire=lambda self,records,directory:poster
        app.show_page('电脑微信');app.source_advanced.set_expanded(True);root.update();assert app.repair_emoji_button.winfo_ismapped();app.repair_emoji_button.invoke()
        deadline=time.monotonic()+10
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        assert not app.busy;app.show_page('聊天归档');root.update();deadline=time.monotonic()+5
        while not any(hasattr(canvas,'image') for _,canvas in app.chat_text.thumbnails) and time.monotonic()<deadline:root.update();time.sleep(.01)
        assert any(hasattr(canvas,'image') for _,canvas in app.chat_text.thumbnails)
        from .inline_emojis import catalog
        inline=next(value['text'] for value in app.chat_text.bubbles.values() if value['row']['content'].startswith('文本表情'))
        assert len(inline.image_names())==2 and inline.get('1.0','end-1c')=='文本表情[流泪]与[捂脸]混排'
        assert len(catalog()['positions'])==109
        with closing(sqlite3.connect(database)) as conn:assert conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]==2
        from .workspace_release_check import verify_workspace
        workspace=verify_workspace(app)
        assert not errors,errors
        return {'workspace_refresh':workspace,'version':__version__,'default_full_history':True,'million_range':True,'offline_no_fetch':True,'legacy_sticker_repaired_and_displayed':True,'messages_not_duplicated':True,'inline_emoticons_displayed':True,'inline_original_preserved':True,'bundled_emoticon_count':109,'synthetic_transport':True,'real_network_requested':False}
    finally:EmojiFetch.acquire=original;app.close()
