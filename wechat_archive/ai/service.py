"""Prepare a bounded request separately from provider transport and Tk widgets."""
from dataclasses import dataclass
from ..errors import ConflictError,ValidationError
from .context import AIContext


@dataclass(frozen=True)
class AIRequest:
    question:str
    scope:object
    model:str|None
    context:AIContext
    expected_epoch:int|None=None
    effort:str|None=None
    fast_mode:bool=False


class AIService:
    def __init__(self,provider):self.provider=provider

    def prepare(self,question,scope,model=None,expected_epoch=None,*,effort=None,fast_mode=False):
        if not isinstance(question,str) or not question.strip() or len(question)>12000:
            raise ValidationError('请输入 1–12000 字的提问。')
        return AIRequest(question.strip(),scope,model,self.provider.capture_ui(scope),expected_epoch,effort,fast_mode)

    def send(self,client,request):
        if not self.provider.is_current_scope(request.scope):raise ConflictError('当前会话已变化，旧请求已撤销。')
        request.context.validate(request.scope)
        context=self.provider.resolve(request.context,request.scope)
        if not self.provider.is_current_scope(request.scope):raise ConflictError('当前会话已变化，旧请求已撤销。')
        options={'context':context,'expected_epoch':request.expected_epoch}
        if request.effort is not None or request.fast_mode:options.update(effort=request.effort,fast_mode=request.fast_mode)
        result=client.send(request.question,request.scope,request.model,**options)
        return {**result,'_ai_context':context} if isinstance(result,dict) else result
