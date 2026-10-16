"""Versioned, scoped JSON-line read API. No listener, database paths or arbitrary plugins."""

import json
import sqlite3

from ..errors import ArchiveError, ConflictError, NotFoundError, ValidationError

VERSION='1.0'
PARAMS={'capabilities':set(),'chunks':{'limit','cursor'},'resolve':{'reference'},
        'search':{'query','limit','min_score'},'status':set()}


class KnowledgeAPI:
    def __init__(self, source, index=None):
        self.source=source
        self.index=index
        if index is not None and index.source.scope_id!=source.scope_id:
            raise ValidationError('API 索引与来源授权范围不一致。')

    def call(self, method, params):
        methods={'capabilities','chunks','resolve'} | ({'search','status'} if self.index else set())
        if not isinstance(method,str) or method not in methods:
            raise ValidationError('未登记或未启用的只读知识方法。')
        if not isinstance(params,dict) or set(params)-PARAMS[method]:
            raise ValidationError('知识方法参数无效；不接受路径、SQL或新的身份范围。')
        if method=='capabilities':
            return {'api_version':VERSION,'read_only':True,'methods':sorted(methods),
                    'scope_id':self.source.scope_id,'scope':{'user_id':self.source.scope.user_id,'peer_id':self.source.scope.peer_id},
                    'coverage':'已归档私聊文本','source_versions':[1,2,3],'reference_version':1,
                    'index_configured':self.index is not None,'arbitrary_plugin_execution':False}
        if method=='chunks': return self.source.page(**params)
        if method=='resolve':
            if set(params)!={'reference'}: raise ValidationError('resolve 需要 reference。')
            return self.source.resolve(params['reference']).to_dict()
        if method=='search':
            if 'query' not in params: raise ValidationError('search 需要 query。')
            return self.index.search(**params)
        if method=='status': return self.index.status()

    def dispatch(self, request):
        request_id=None
        try:
            if not isinstance(request,dict) or set(request)!={'version','id','method','params'}:
                raise ValidationError('API 请求须含 version/id/method/params。')
            request_id=request['id']
            if not (type(request_id) is int and 0<=request_id<2**63 or isinstance(request_id,str) and 1<=len(request_id)<=64):
                request_id=None; raise ValidationError('API 请求 ID 无效。')
            if request['version']!=VERSION: raise ValidationError('不支持的 API 版本。')
            result=self.call(request['method'],request['params'])
            if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>256000:
                raise ValidationError('响应超过预算，请缩小读取页。')
            return {'version':VERSION,'id':request_id,'ok':True,'result':result}
        except ArchiveError as error:
            code='not_found' if isinstance(error,NotFoundError) else 'conflict' if isinstance(error,ConflictError) else 'validation'
            return {'version':VERSION,'id':request_id,'ok':False,'error':{'code':code,'message':str(error)}}
        except (OSError,sqlite3.Error,TypeError,ValueError):
            return {'version':VERSION,'id':request_id,'ok':False,
                    'error':{'code':'backend','message':'知识读取未完成，请检查归档和索引；没有更改原文。'}}

    def serve(self, input_stream, output_stream):
        while True:
            line=input_stream.readline(65537)
            if not line: return 0
            if len(line.encode('utf-8'))>65536:
                response={'version':VERSION,'id':None,'ok':False,'error':{'code':'validation','message':'请求超过64 KiB预算，连接结束。'}}
                output_stream.write(json.dumps(response,ensure_ascii=False)+'\n'); output_stream.flush(); return 2
            try: request=json.loads(line)
            except (ValueError,TypeError): request=None
            output_stream.write(json.dumps(self.dispatch(request),ensure_ascii=False)+'\n'); output_stream.flush()
