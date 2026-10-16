"""仅用于离线协议测试；不会调用网络或真实账号。"""
import json
import os
from pathlib import Path
import sys

trace = Path(sys.argv[1])
account = None
active = None


def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


def notify(method, params):
    emit({'method':method,'params':params})


for line in sys.stdin:
    message = json.loads(line)
    with trace.open('a',encoding='utf-8') as handle:
        handle.write(json.dumps(message,ensure_ascii=False)+'\n')
    method = message.get('method'); request_id = message.get('id'); params = message.get('params',{})
    result = {}
    if method == 'initialize':
        result = {'userAgent':'offline_fixture','codexHome':os.environ['CODEX_HOME']}
    elif method == 'account/read':
        result = {'account':account,'requiresOpenaiAuth':True}
    elif method == 'account/login/start':
        result = {'type':'chatgpt','loginId':'unit-login','authUrl':'https://auth.openai.com/oauth/authorize?state=unit'}
        account = {'type':'chatgpt','email':'unit@example.invalid','planType':'plus'}
    elif method == 'account/logout':
        account = None
    elif method == 'model/list':
        result = {'data':[{'id':'unit-model','model':'unit-model','displayName':'测试模型','hidden':False}],'nextCursor':None}
    elif method == 'thread/start':
        result = {'thread':{'id':'unit-thread'},'instructionSources':[]}
    elif method == 'thread/resume':
        result = {'thread':{'id':params['threadId']},'instructionSources':[]}
    elif method == 'turn/start':
        active = {'id':'unit-turn','status':'inProgress','error':None}
        notify('turn/started',{'threadId':'unit-thread','turn':active})
        result = {'turn':active}
    elif method == 'turn/interrupt':
        notify('turn/completed',{'threadId':'unit-thread','turn':{'id':'unit-turn','status':'interrupted','error':None}})
    elif method is None and 'result' in message:
        result = message['result']
        text = '已查询授权范围。' if result.get('success') else '查询失败。'
        notify('item/agentMessage/delta',{'threadId':'unit-thread','turnId':'unit-turn','itemId':'unit-answer','delta':text[:4]})
        notify('item/agentMessage/delta',{'threadId':'unit-thread','turnId':'unit-turn','itemId':'unit-answer','delta':text[4:]})
        notify('item/completed',{'threadId':'unit-thread','turnId':'unit-turn','item':{'type':'agentMessage','id':'unit-answer','phase':'final_answer','text':text}})
        notify('turn/completed',{'threadId':'unit-thread','turn':{'id':'unit-turn','status':'completed','error':None}})
        continue
    if request_id is not None:
        emit({'id':request_id,'result':result})
    if method == 'turn/start' and '--hold' not in sys.argv:
        emit({'id':'server-tool-1','method':'item/tool/call','params':{'threadId':'unit-thread','turnId':'unit-turn',
             'callId':'unit-call','tool':'archive_messages','namespace':None,'arguments':{'limit':2}}})
    elif method == 'account/login/start':
        notify('account/login/completed',{'loginId':'unit-login','success':True,'error':None})
        notify('account/updated',{'authMode':'chatgpt','planType':'plus'})
