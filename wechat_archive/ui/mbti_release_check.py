"""Packaged interface checks; generated records only, no model request."""


def verify_mbti_ui(app):
    from ..branding import APP_NAME
    from ..ai.personality import mbti_prompt
    from .mbti_panel import participants
    root=app.root;panel=app.agent_panel
    assert app.brand_label.cget('text')==APP_NAME
    assert str(panel.parameters_button.cget('compound'))=='right' and panel.parameters_button.cget('image')
    assert panel.parameter_caption.get()==(panel.selected_model_name() or app.tr('选择模型'))
    captions=[w.cget('text') for w in app.descendants(app.header) if w.winfo_class()=='TButton']
    assert 'MBTI' in captions and '打开归档' not in captions and '新建归档' not in captions
    app.mbti_button.invoke();root.update();window=app.mbti_popup
    assert window.winfo_exists() and window.mbti_start.instate(['disabled'])
    assert window.mbti_start.winfo_rooty()+window.mbti_start.winfo_height()<=window.winfo_rooty()+window.winfo_height()
    assert participants(app,'当前身份的所有私聊')[0]['id']==app.owner_id
    window.destroy()
    panel._clear();panel._add('你','界面问题');panel._add('Codex · 回答','带引用的界面回答 [消息 #1]')
    assert panel.transcript.get('1.0','end-1c')=='界面问题\n\n带引用的界面回答 [消息 #1]'
    assert panel.transcript.tag_cget('turn_user','background')!=panel.transcript.tag_cget('turn_codex','background')
    panel.active=True;panel._controls();before=panel.reply_indicator.get()
    root.after(720,root.quit);root.mainloop();after=panel.reply_indicator.get()
    assert before!=after and before.startswith('千丝万绪') and after.startswith('千丝万绪')
    panel.active=False;panel._controls();assert not panel.reply_indicator.get()
    assert 'archive_messages' in mbti_prompt(app.owner_id,'自建对象','当前会话')
    assert not hasattr(app.detect_button,'_action_hint')
    app.nav_note.invoke();root.update();statistics=app.statistics_panel
    import time
    deadline=time.monotonic()+10
    while statistics.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
    assert statistics.data and statistics.data['summary']['total']>0
    app.show_page('聊天归档')
    return {'top_entry':True,'version_header':True,'hidden_role_labels':True,'distinct_dialogue_colors':True,
            'animated_suffix':True,'mbti_scope_and_login_gate':True,'popup_actions_fit':True,'local_statistics':True,'real_inference':False}
