"""Exercise production background browsing in the frozen package using generated data."""
import time


def verify_large_ui(app):
    root=app.root;before=(app.background_browsing,app.search_scope.get(),app.search_word.get())
    try:
        app.show_page('聊天归档')
        app.background_browsing=True;app.search_scope.set('全部会话');app.search_word.set('');app.load_messages()
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            root.update()
            if app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False) and not getattr(app.chat_text,'cleanup_job',None):break
            time.sleep(.005)
        assert app.browser_reads.future is None and not getattr(app.chat_text,'rendering',False)
        assert app.message_total>=3 and len(app.chat_text.rows)==len(app.message_rows)
        assert not app.header_archive.winfo_ismapped()
        assert 'Quiet.TButton' in str(app.copilot_button.cget('style'))
        assert not hasattr(app.agent_panel.power_popover,'reset_button')
        return {'background_reads':True,'incremental_message_rows':True,'internal_filename_hidden':True,'unframed_codex_entry':True,'no_strength_reset':True}
    finally:
        app.background_browsing=before[0];app.search_scope.set(before[1]);app.search_word.set(before[2]);app.load_messages();root.update()
