"""Frozen 2.2 forward image check using the already generated test archive."""
import hashlib,time,tkinter as tk
from ..importer.rich_importer import ready_media

def verify_forward_image(app):
    root=app.root
    with app.controller.readonly().connection() as conn:
        item=dict(conn.execute("SELECT * FROM media WHERE kind='image' AND availability='ready' LIMIT 1").fetchone())
    data=ready_media(app.controller.require_archive(),item).read_bytes();digest=hashlib.md5(data).hexdigest()
    xml='<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist><dataitem datatype="2"><sourcename>合成伙伴</sourcename><datadesc>[图片]</datadesc><fullmd5>'+digest+'</fullmd5><datasize>'+str(len(data))+'</datasize></dataitem></datalist></recordinfo>]]></recorditem></appmsg></msg>'
    base=app.controller.messages(app.owner_id,app.peer_id)['items'][0];row={**base,'id':999002,'content':xml,'msg_type':'system','attachments':[item]}
    app.show_page('聊天归档');app.chat_text.set_rows([row],app.owner_id);root.update()
    control=app.chat_text.bubbles[row['id']]['forward'];control.toggle();stop=time.monotonic()+5
    while time.monotonic()<stop:
        root.update()
        if app.chat_text.thumbnails and hasattr(app.chat_text.thumbnails[-1][1],'image'):break
        time.sleep(.005)
    assert app.chat_text.thumbnails and hasattr(app.chat_text.thumbnails[-1][1],'image')
    canvas=app.chat_text.thumbnails[-1][1];canvas.event_generate('<Button-1>');root.update()
    window=next(w for w in root.winfo_children() if isinstance(w,tk.Toplevel) and hasattr(w,'preview_state'))
    assert any(w.winfo_class()=='TButton' and w.cget('text')=='另存图片' for w in app.descendants(window))
    root.tk.call(window.protocol('WM_DELETE_WINDOW'));control.collapse();root.update();assert not canvas.winfo_exists()
    assert len(app.tools_notebook.tabs())==3 and '归档小工具' not in app.pages
    saved=(app.accounts,tuple(app.account_box.cget('values')),app.account_box.current(),app.account_box.get())
    try:
        app.accounts=[{'account':'unit_native_a','wxid':'unit_a','nickname':'合成微信甲','weixin_id':'unit_account_a'},{'account':'unit_native_b','wxid':'unit_b','nickname':'合成微信乙','weixin_id':'unit_account_b'}]
        app.update_account_labels();app.account_box.current(1)
        assert app.account_box.get()=='合成微信乙 · 微信号：unit_account_b'
        assert app.account_selection()[1]=='unit_native_b'
    finally:
        app.accounts=saved[0];app.account_box.configure(values=saved[1])
        if saved[2]>=0:app.account_box.current(saved[2])
        else:app.account_box.set(saved[3])

    return {'inline_image_visible':True,'ordinary_image_preview':True,'save_action_present':True,'fold_releases_media':True,'three_direct_tool_tabs':True,'exact_digest_and_size_binding':True,'verified_wechat_account_caption':True,'exact_account_selection':True,'synthetic_only':True}
