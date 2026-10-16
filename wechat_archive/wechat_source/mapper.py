"""已知来源记录 → chat-exchange；未知/歧义记录保留在来源报告。"""

import hashlib
import json
from datetime import datetime,timezone
from urllib.parse import quote

from ..importer.records import LoadedDocument
from ..importer.validator import DocumentError


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def normalize_export(payload,provenance):
    owner,peer=payload['account']['wxid'],payload['conversation']['wxid']
    namespace='wechat:'+quote(owner,safe='')
    chat_id='private:'+quote(peer,safe='')
    messages=[];quarantine=[];seen={};order_keys={}
    def retain(index,row,code,reason):
        quarantine.append({'index':index,'raw_type':row.get('raw_type') if isinstance(row,dict) else None,
                           'raw_payload':row,'parse_status':code,'reason':reason})
    def fail(reason):
        error=DocumentError(reason)
        error.source_metadata={'id':namespace,'metadata':{'external_parse':{'raw_count':len(payload['records']),
            'accepted_text_count':0,'quarantined_count':len(quarantine),'quarantine_records':quarantine},**provenance}}
        raise error
    required={'local_id','source_database','source_message_id','source_id_kind','sender_wxid','timestamp','content','raw_type','raw_payload'}
    for index,row in enumerate(payload['records'],1):
        if not isinstance(row,dict) or set(row)!=required:
            retain(index,row,'invalid_fields','记录字段不符合已登记来源契约');continue
        if row['raw_type']!=1 or type(row['raw_type']) is not int:
            retain(index,row,'unsupported_message_type','非文本或未知类型已保存原记录，不进入聊天库');continue
        if not isinstance(row['sender_wxid'],str) or row['sender_wxid'] not in {owner,peer}:
            retain(index,row,'unknown_sender','发送者没有解析为本私聊两个稳定身份之一');continue
        if type(row['local_id']) is not int or row['local_id']<=0 or not isinstance(row['source_id_kind'],str) or row['source_id_kind'] not in {'local','server'} or not isinstance(row['source_message_id'],str) or not row['source_message_id'].strip() or not isinstance(row['source_database'],str) or not row['source_database'].strip():
            retain(index,row,'invalid_source_id','缺少分片或稳定来源消息标识');continue
        if type(row['timestamp']) is not int or not 0<=row['timestamp']<4102444800:
            retain(index,row,'invalid_time','不是登记范围内的 Unix 秒整数');continue
        raw=row['raw_payload'].get('database_row') if isinstance(row['raw_payload'],dict) else None
        if not isinstance(raw,dict) or type(raw.get('local_type')) is not int or raw.get('local_type')!=1 or type(raw.get('local_id')) is not int or raw.get('local_id')!=row['local_id'] or raw.get('shard')!=row['source_database'] or raw.get('sender_username')!=row['sender_wxid'] or type(raw.get('create_time')) is not int or raw.get('create_time')!=row['timestamp'] or type(raw.get('sort_seq')) is not int:
            retain(index,row,'source_evidence_mismatch','来源数据库记录与导出身份/时间/分片不一致');continue
        if not isinstance(row['content'],str) or not row['content'].strip() or not isinstance(raw.get('content'),str) or raw['content']!=row['content']:
            retain(index,row,'unsupported_text_storage','本 MVP 只接受已核验的数据库原始文本，二进制/占位正文保留未处理');continue
        if row['source_id_kind']=='server' and str(raw.get('server_id'))!=row['source_message_id'] or row['source_id_kind']=='local' and str(row['local_id'])!=row['source_message_id']:
            retain(index,row,'source_evidence_mismatch','来源消息 ID 与原记录不一致');continue
        source_identity=[owner,peer,row['source_database'],row['source_id_kind'],row['source_message_id']]
        ref='external-msg:'+digest(source_identity)
        sender=row['sender_wxid'];receiver=peer if sender==owner else owner
        timestamp=datetime.fromtimestamp(row['timestamp'],timezone.utc).isoformat(timespec='microseconds').replace('+00:00','Z')
        material=[sender,receiver,timestamp,row['content']]
        if ref in seen:
            if seen[ref]!=material:
                retain(index,row,'source_id_conflict','同一来源 ID 的内容冲突')
                fail('同一来源复合消息 ID 指向不同内容，拒绝覆盖')
            retain(index,row,'duplicate_source_record','重复来源记录已保留，不重复生成消息');continue
        seen[ref]=material
        order_keys[ref]=(row['timestamp'],raw['sort_seq'],row['source_database'],row['local_id'])
        messages.append({'id':ref,'sender_id':sender,'receiver_id':receiver,'chat_id':chat_id,'timestamp':timestamp,
                         'type':'text','content':row['content'],'source_id':json.dumps(source_identity,ensure_ascii=False,separators=(',',':')),
                         'source_hash':digest(row['raw_payload'])})
    if payload['records'] and not messages:fail('没有可核验的真实文本记录，未写入归档；原始导出文件和隔离记录保留')
    messages.sort(key=lambda message:order_keys[message['id']])
    metadata={'adapter':'external-export','source_platform':'wechat','source_account':owner,'provider':payload['provider'],
              'capture':payload['capture'],**provenance,'source_databases':sorted({row['source_database'] for row in payload['records'] if isinstance(row,dict) and isinstance(row.get('source_database'),str)}),
              'external_parse':{'raw_count':len(payload['records']),'accepted_text_count':len(messages),'quarantined_count':len(quarantine),'quarantine_records':quarantine}}
    users=[{'id':person['wxid'],'external_id':namespace+':'+quote(person['wxid'],safe=''),'nickname':person['nickname'],'avatar':None} for person in (payload['account'],payload['conversation'])]
    return LoadedDocument({'format':'chat-exchange','format_version':'1.0','source':{'id':namespace,'name':'微信真实结构化导出','account_id':owner,'metadata':metadata},
                           'users':users,'chats':[{'id':chat_id,'external_id':chat_id,'type':'private','title':payload['conversation']['nickname'],'participant_ids':sorted([owner,peer])}],
                           'messages':messages,'media':[]}, identity_strategy='source-id-v1')
