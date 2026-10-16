"""Rounded branding and mapped resizing in the actual frozen application."""
import time

def verify_rounded_resize(app):
    window=app.root;tool=app.toolbox_panel.workshop
    assert window.tk.call(str(app.window_logo),'transparency','get',0,0)
    app.show_page('文字小工坊');raw='原文😀 hello\n缩放后继续编辑 hello';tool.set_text(raw)
    editor=str(tool.text);tool.text.tag_add('sel','1.0','1.2')
    for width,height in ((980,700),(1450,850),(1100,760)):
        window.geometry(f'{width}x{height}');window.update()
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        window.update()
        if not app.layout_job and not app.resize_viewport.pinned:break
        time.sleep(.01)
    assert not app.resize_viewport.pinned and app.workspace_panes.winfo_viewable()
    assert str(tool.text)==editor and tool.text.get('1.0','end-1c')==raw
    assert tool.text.get('sel.first','sel.last')=='原文'
    assert abs(app.workspace_panes.winfo_width()-app.resize_viewport.winfo_width())<=1
    viewport=app.resize_viewport;main=viewport.master
    assert viewport.winfo_x()+viewport.winfo_width()<=main.winfo_width()
    assert abs(viewport.winfo_height()-main.winfo_height())<=1
    tool.open_find();window.update();assert tool.find_window.winfo_viewable()
    tool.find.set('hello');tool.replacement.set('world');tool.replace(True)
    assert tool.text.get('1.0','end-1c')==raw.replace('hello','world')
    tool.undo(False);assert tool.text.get('1.0','end-1c')==raw
    tool.find_window.withdraw();app.show_page('聊天归档');window.update()
    return {'rounded_window_icon':True,'mapped_workspace_resize':True,'final_geometry_fills_viewport':True,'original_text_and_selection_retained':True,'find_replace_and_undo':True,'synthetic_only':True,'source_or_model_request':False}
