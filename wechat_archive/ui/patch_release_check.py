"""Frozen 2.1.1 checks on generated content, with no WeChat or model calls."""
import time,tkinter as tk
from pathlib import Path
from PIL import Image


def verify_patch(app):
    root=app.root
    xml='<msg><appmsg><type>19</type><recorditem><![CDATA[<recordinfo><datalist>'+''.join(f'<dataitem datatype="1"><sourcename>合成伙伴</sourcename><sourcetime>2026-10-16</sourcetime><datadesc>原文{i}[流泪]</datadesc></dataitem>' for i in range(10))+'</datalist></recordinfo>]]></recorditem></appmsg></msg>'
    base=app.controller.messages(app.owner_id,app.peer_id)['items'][0];row={**base,'id':999001,'content':xml,'msg_type':'system','attachments':[]}
    app.show_page('聊天归档');app.chat_text.set_rows([row],app.owner_id);root.update()
    card=app.chat_text.bubbles[row['id']]['forward'];assert not card.expanded and not card.rendered
    card.heading.invoke();deadline=time.monotonic()+5
    while (len(card.rendered)<10 or card.resize_job or card.rendered[0][2] is None) and time.monotonic()<deadline:root.update();time.sleep(.005)
    assert len(card.rendered)==10 and card.rendered[0][2].get('1.0','end-1c')=='原文0[流泪]'
    assert len(card.rendered[0][2].image_names())==1
    card.menu.invoke(1);assert root.clipboard_get()==xml
    card.fold.invoke();root.update();assert not card.expanded and not card.rendered
    app.capsule_button.invoke();root.update();assert app.current_page=='时光胶囊' and app.toolbox_panel.capsule.memory.winfo_ismapped()
    assert int(app.capsule_button.grid_info()['row'])<int(app.nav_note.grid_info()['row'])
    app.memory_button.invoke();root.update();assert app.memory_popup.window.winfo_ismapped() and '随机回忆' not in app.tab_routes
    for name in ('文字小工坊',):
        app.show_page(name);root.update();notebook,tab=app.tab_routes[name]
        assert notebook is app.tools_notebook and notebook.select()==str(tab)
    picture=Path(app.controller.database).parent/'patch_avatar.png';Image.new('RGB',(64,64),'#df9494').save(picture)
    app.show_page('聊天归档');app.contact_tree.set_rows([{'id':883,'nickname':'合成头像','wxid':'release_patch_peer','avatar':str(picture),'message_count':1}]);root.update()
    content=app.contact_tree.cards['883'][0].content;canvas=next(w for w in content.winfo_children() if isinstance(w,tk.Canvas))
    assert not bool(root.tk.call(str(canvas.avatar_image),'transparency','get',app.theme.u(4),app.theme.u(4)))
    assert bool(root.tk.call(str(canvas.avatar_image),'transparency','get',0,0))
    return {'folded_default':True,'inline_normal_messages':10,'forward_inline_emoticon':True,'raw_forward_copy_unchanged':True,'fold_releases_widgets':True,'capsule_bottom_above_statistics':True,'random_memory_bottom_utility':True,'wechat_rounded_square_avatar':True,'model_requests':False,'wechat_source_read':False}
