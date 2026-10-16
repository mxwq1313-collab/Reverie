"""Second client shares scoped knowledge services; no fallback database initialization."""

import json
import sys

from ..agent import ArchiveScope
from ..errors import ValidationError
from .api import KnowledgeAPI
from .index import KnowledgeIndex
from .providers import LexicalEmbedding, OllamaEmbedding, OllamaEndpoint
from .rag import OllamaGenerator, RagService
from .source import KnowledgeSource


def add_parser(commands):
    parser=commands.add_parser('knowledge',help='限定范围的原文切片、独立索引、本地证据问答及只读API')
    parser.add_argument('--user',type=int,required=True,dest='user_id')
    parser.add_argument('--peer',type=int,dest='peer_id')
    parser.add_argument('--index',help='独立知识索引文件；不能选择原归档')
    parser.add_argument('--embedding',choices=('lexical','ollama'),default='lexical')
    parser.add_argument('--endpoint',default='http://127.0.0.1:11434')
    parser.add_argument('--embedding-model',help='已安装本地向量模型的精确名称')
    parser.add_argument('--model',help='已安装本地回答模型的精确名称')
    sub=parser.add_subparsers(dest='knowledge_action',required=True)
    sub.add_parser('capabilities',help='列出版本、授权范围和当前实际方法')
    chunks=sub.add_parser('chunks'); chunks.add_argument('--limit',type=int,default=30); chunks.add_argument('--cursor')
    resolve=sub.add_parser('resolve'); resolve.add_argument('reference',help='完整ChunkRef JSON')
    build=sub.add_parser('build'); build.add_argument('--rebuild',action='store_true')
    sub.add_parser('status')
    for name in ('search','ask'):
        p=sub.add_parser(name); p.add_argument('query'); p.add_argument('--limit',type=int,default=5); p.add_argument('--min-score',type=float,default=.2)
    sub.add_parser('api',help='stdio JSON-lines API v1.0；不监听网络、不写原文/索引、不执行插件')


def execute(args):
    if args.db is None: raise ValidationError('知识操作必须明确指定 --db 已有归档。')
    source=KnowledgeSource(ArchiveScope(args.db,args.user_id,args.peer_id))
    index=None
    if args.index:
        provider=LexicalEmbedding() if args.embedding=='lexical' else OllamaEmbedding(OllamaEndpoint(args.endpoint),args.embedding_model)
        index=KnowledgeIndex(args.index,source,provider)
    api=KnowledgeAPI(source,index); action=args.knowledge_action
    if action=='api': return None,api.serve(sys.stdin,sys.stdout)
    if action=='capabilities': return api.call(action,{}),0
    if action=='chunks': return api.call(action,{'limit':args.limit,'cursor':args.cursor}),0
    if action=='resolve':
        try: ref=json.loads(args.reference)
        except ValueError as error: raise ValidationError('reference 须为 ChunkRef JSON。') from error
        return api.call(action,{'reference':ref}),0
    if index is None: raise ValidationError('此知识操作需要显式 --index 独立索引路径。')
    if action=='build': return index.sync(rebuild=args.rebuild),0
    if action=='status': return api.call(action,{}),0
    if action=='search': return api.call(action,{'query':args.query,'limit':args.limit,'min_score':args.min_score}),0
    if action=='ask':
        if not args.model: raise ValidationError('本地问答需要 --model 已安装回答模型。')
        return RagService(index,OllamaGenerator(OllamaEndpoint(args.endpoint),args.model)).ask(args.query,args.limit,args.min_score),0
    raise ValidationError('未知知识命令。')
