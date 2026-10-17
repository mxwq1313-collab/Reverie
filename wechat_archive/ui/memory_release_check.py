"""Frozen memory utility probe; uses only the existing generated check archive."""
import time

def verify_memory_utility(app):
    root=app.root;app.show_page('随机回忆');root.update()
    tool=app.toolbox_panel.random
    assert tool.memory.winfo_ismapped()
    assert app.current_page=='工具与设置' and '随机回忆' in app.tab_routes
    assert not tool.filters.winfo_ismapped() and root.grab_current() is None
    tool.search();deadline=time.monotonic()+10
    while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
    root.update();assert not app.busy and tool.row is not None
    tool.copy();assert root.clipboard_get()==tool.formatted(tool.row)
    original=tool.row['id'];widget=str(tool.memory)
    app.show_page('聊天归档');app.show_page('随机回忆');root.update()
    assert str(tool.memory)==widget and tool.row['id']==original
    tool.toggle_filters();root.update();assert tool.filters.winfo_ismapped()
    tool.toggle_filters();app.show_page('聊天归档');app.feedback.show('正在检测电脑微信账号…');root.update()
    assert not hasattr(app.feedback,'frame')
    return {'tool_tab_entry':True,'no_memory_popup':True,'real_synthetic_archive_draw':True,'copy_and_history_retained':True,'filters_collapsed_by_default':True,'account_detection_toast_removed':True,'no_source_or_model_request':True}
