"""One active read and one replaceable pending request; Tk work remains on the UI thread."""
from concurrent.futures import Future
import threading


class BrowserReads:
    def __init__(self,root,blocked=lambda:False):
        self.root=root;self.condition=threading.Condition();self.pending=None;self.thread=None
        self.blocked=blocked
        self.future=None;self.cancel=None;self.serial=0;self.job=None;self.closed=False;self.kind=None
    def submit(self,kind,work,done,failed):
        if self.closed:return
        if self.cancel:self.cancel.set()
        if self.future:self.future.cancel()
        self.serial+=1;self.cancel=threading.Event();self.kind=kind
        self.future=Future();self.done=done;self.failed=failed
        with self.condition:
            self.pending=(self.future,work,self.cancel);self.condition.notify()
            if self.thread is None:
                self.thread=threading.Thread(target=self.worker,daemon=True,name='sixu-reader');self.thread.start()
        if self.job is None:self.job=self.root.after(15,self.poll)
    def worker(self):
        while True:
            with self.condition:
                while self.pending is None and not self.closed:self.condition.wait()
                if self.closed:return
                future,work,cancel=self.pending;self.pending=None
            if not future.set_running_or_notify_cancel():continue
            try:future.set_result(work(cancel))
            except BaseException as error:future.set_exception(error)
    def poll(self):
        self.job=None
        if self.closed or self.future is None:return
        if self.blocked():self.job=self.root.after(100,self.poll);return
        if self.future.done():
            future=self.future;done=self.done;failed=self.failed;self.future=None;self.kind=None
            try:value=future.result();done(value)
            except Exception as error:failed(error)
        if self.future is not None and self.job is None:self.job=self.root.after(25,self.poll)
    def close(self):
        self.closed=True
        if self.cancel:self.cancel.set()
        if self.future:self.future.cancel()
        if self.job:self.root.after_cancel(self.job)
        self.future=None;self.job=None
        with self.condition:self.pending=None;self.condition.notify()


class AsyncBrowserMixin:
    def read_problem(self,error):
        self.status.set('读取未完成：'+str(error))
        if not self.message_rows:self.show_browser_state('failed',str(error))
    def read_contacts_async(self):
        if self.owner_id is None or self.browser_reads.kind=='open':return
        owner=self.owner_id;word=self.contact_keyword.get();token=self.controller.archive_view_token()
        reader=self.controller.read_snapshot(None)
        def work(cancel):reader._read_cancel=cancel;return reader.contacts(owner,word)
        def done(rows):
            if (owner,word)!=(self.owner_id,self.contact_keyword.get()):return
            if token!=self.controller.archive_view_token():self.status.set('归档已变化，请重新搜索。');return
            self.load_contacts(_prepared=rows)
        self.status.set('正在查找会话…');self.browser_reads.submit('contacts',work,done,self.read_problem)
    def read_messages_async(self,more=False):
        if self.owner_id is None or self.browser_reads.kind=='open':return
        peer=None if self.search_scope.get()=='全部会话' else self.peer_id
        if peer is None and self.search_scope.get()!='全部会话':self.show_browser_state('no_chats');return
        query=(self.owner_id,peer,self.search_word.get(),self.start_date.get(),self.end_date.get())
        if more and query!=getattr(self,'loaded_query',None):more=False
        token=self.controller.archive_view_token();offset=self.loaded_offset+len(self.message_rows) if more else 0
        if more and token!=getattr(self,'loaded_token',None):self.status.set('归档已变化，不能追加旧分页；请重新搜索。');return
        reader=self.controller.read_snapshot(None)
        def work(cancel):reader._read_cancel=cancel;return reader.messages(*query,offset)
        def done(result):
            current=(self.owner_id,None if self.search_scope.get()=='全部会话' else self.peer_id,self.search_word.get(),self.start_date.get(),self.end_date.get())
            if current!=query:return
            if token!=self.controller.archive_view_token():self.status.set('归档已变化，请重新搜索。');return
            self.load_messages(more,_prepared=result);self.status.set('正在显示聊天记录…' if getattr(self.chat_text,'rendering',False) else '已加载聊天记录。')
        self.more_button.configure(state='disabled');self.status.set('正在查找聊天记录…')
        self.browser_reads.submit('messages',work,done,self.read_problem)
    def open_browser_archive(self,archive=None):
        initial=self.controller.database;reader=self.controller.read_snapshot(None)
        panel=getattr(self,'agent_panel',None)
        if panel and panel.client:panel.client.revoke_tools()
        def work(cancel):
            reader._read_cancel=cancel
            if archive:reader.open_archive(archive)
            elif not reader.database and self.ui_settings['restore_recent']:reader.restore_archive()
            if reader.database:
                users=reader.users();saved=reader.view_state();ids=[row['id'] for row in users]
                owner=saved.get('owner_id') if saved.get('owner_id') in ids else ids[0] if ids else None
                if owner is not None:reader.contacts(owner)
            return reader.database,reader.archive_view_token() if reader.database else None
        def done(result):
            path,token=result
            if self.controller.database!=initial:return
            if path and token!=reader.archive_view_token():self.read_problem('归档已变化，请重新打开。');return
            self.controller.database=path
            if path:
                settings=self.controller.settings();settings['last_archive']=str(path);self.controller.save_settings(settings)
            self.refresh_archive();self.localize_ui()
        self.status.set('正在打开归档…');self.browser_reads.submit('open',work,done,self.read_problem)
