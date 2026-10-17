"""Rounded branding and mapped resizing in the actual frozen application."""
import time

def verify_rounded_resize(app):
    window=app.root;app.show_page('随机回忆');text=app.toolbox_panel.random.memory
    assert window.tk.call(str(app.window_logo),'transparency','get',0,0)
    raw='原文😀 hello\n缩放后保留原文';text.configure(state='normal');text.delete('1.0','end');text.insert('1.0',raw);text.tag_add('sel','1.0','1.2');text.configure(state='disabled');editor=str(text)
    for width,height in ((980,700),(1450,850),(1100,760)):
        window.geometry(f'{width}x{height}');window.update()
        assert app.workspace_panes.winfo_viewable()
        assert abs(app.workspace_panes.winfo_width()-app.resize_viewport.winfo_width())<=1
    assert str(text)==editor and text.get('1.0','end-1c')==raw and text.get('sel.first','sel.last')=='原文'
    followup=verify_resize_followup(app)
    app.show_page('聊天归档');window.update()
    return {'rounded_window_icon':True,'mapped_workspace_resize':True,'final_geometry_fills_viewport':True,'original_text_and_selection_retained':True,'synthetic_only':True,'source_or_model_request':False,'followup':followup}

def verify_resize_followup(app):
    """Exercise continuously mapped controls and fast-mode UI on generated data."""
    root=app.root;unmaps=[]
    binding=app.workspace_panes.bind('<Unmap>',lambda e:unmaps.append(e.widget) if e.widget is app.workspace_panes else None,add='+')
    try:
        for width,height in ((1240,800),(980,700),(1450,850),(1100,760)):
            root.geometry(f'{width}x{height}');root.update()
            assert app.workspace_panes.winfo_viewable()
            assert abs(app.workspace_panes.winfo_width()-app.resize_viewport.winfo_width())<=1
        assert not unmaps and not hasattr(app,'native_resize')
    finally:app.workspace_panes.unbind('<Unmap>',binding)
    panel=app.agent_panel;old=panel.fast_mode.get();panel.fast_mode.set(True)
    if hasattr(panel,'power_popover'):panel.power_popover.show()
    else:panel.parameters_button.invoke()
    root.update();view=panel.power_popover
    assert panel.fast_button.icon_key[1] in ('#8b5cf6','#c4b5fd')
    assert view.animation_job and (view.slider.find_withtag('fast_flow') or view.slider.find_withtag('fast_pulse'))
    panel.parameters_popup.withdraw();root.update();assert view.animation_job is None
    panel.fast_mode.set(old);app.feedback.show('验收操作已完成。');root.update()
    assert not hasattr(app.feedback,'frame') and app.status.get()=='验收操作已完成。'
    from ..identity import canonical_identity
    assert canonical_identity('wechat:unit_account:unit_peer%20')=='wechat:unit_account:unit_peer'
    return {'live_native_widgets':True,'workspace_never_unmapped':True,'bitmap_substitution':False,'purple_fast_icon':True,'fast_effect_stops_when_hidden':True,'status_only_feedback':True,'canonical_identity_module':True}
