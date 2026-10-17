"""Packaged workspace contracts; synthetic messages and local widgets only."""
import time


def verify_workspace(app):
    root=app.root;panel=app.agent_panel
    raw='## 归档验收\n\n- **重点**：中文😀[消息 #1]\n\n`code`'
    panel._clear();panel._add('Codex · 回答',raw);root.update()
    assert panel.transcript.get('1.0','end-1c')==raw
    assert panel.transcript.tag_ranges('md_bold') and panel.transcript.tag_ranges('md_reference_marker')
    labels=[app.tools_notebook.tab(tab,'text') for tab in app.tools_notebook.tabs()]
    assert labels==['归档管理','语义检索','随机回忆'],labels
    app.show_page('报告与设置');root.update();assert app.current_page=='设置'
    app.show_page('随机回忆');root.update();box=app.toolbox_panel
    assert box.active=='随机回忆' and box.random.memory.winfo_ismapped() and not hasattr(box,'workshop')
    from .app_logo import original
    assert app.window_logo.width()==64 and original().startswith(b'\x89PNG')
    app.feedback.show('验收操作已完成。');root.update();assert app.status.get()=='验收操作已完成。' and not hasattr(app.feedback,'frame')
    app.feedback.hide();app.show_page('数据管理');root.update();assert app.user_tree.winfo_exists()
    from .patch_release_check import verify_patch
    patch=verify_patch(app)
    from .forward_release_check import verify_forward_image
    media=verify_forward_image(app)
    from .memory_release_check import verify_memory_utility
    memory=verify_memory_utility(app)
    from .resize_release_check import verify_rounded_resize
    resize=verify_rounded_resize(app)
    return {'rounded_resize_2_2_2':resize,'memory_utility_2_2_1':memory,'forward_image_2_2':media,'patch_2_1_1':patch,'answer_markdown':True,'raw_unicode_preserved':True,'compact_citations':True,'reports_in_settings':True,'tool_tabs':labels,'workshop_removed':True,'independent_tool_pages':True,'cat_logo':True,'feedback_receipt_visible':True,'no_model_request':True}
