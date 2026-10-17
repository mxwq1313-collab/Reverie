"""Operation feedback stays in the existing status bar; no floating receipt UI."""
class ActionFeedback:
    def __init__(self,app):self.app=app;self.closed=False;self.message='';self.tone='info'
    def attach(self,widget):pass
    def receipt(self,label,before):
        if not self.closed:self.message=self.app.status.get()
    def show(self,message,tone=None):
        if self.closed:return
        self.message=message;self.tone=tone or ('attention' if any(x in message for x in ('失败','未完成','请选择','未保存','未复制','没有')) else 'info')
        self.app.status.set(message)
    def hide(self):pass
    def close(self):self.closed=True
