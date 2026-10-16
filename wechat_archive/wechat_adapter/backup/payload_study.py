"""元信息 wire 结构、有限载荷取样与解码可行性；不写聊天数据库。"""

import hashlib
import json
import math
import os
from collections import Counter
from dataclasses import dataclass,field
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4

from ..base import UnsupportedWeChatSource
from .analyzer import RMFHFormatAnalyzer,_envelope_from_edges
from .bounded_reader import ReadBudget,SamplingError,read_region
from .payload_decoder import DecoderRegistry,compression_signature
from .parser import find_devices
from .reader import checked_path,file_stamp,read_edges
from .wire_probe import probe_wire,text_shape


def byte_evidence(data):
    counts=Counter(data)
    entropy=-sum(n/len(data)*math.log2(n/len(data)) for n in counts.values()) if data else 0.0
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
            'prefix16_sha256':hashlib.sha256(data[:16]).hexdigest(),
            'entropy_bits_per_byte':round(entropy,6),'zero_fraction':round(data.count(0)/max(1,len(data)),6),
            'ascii_printable_fraction':round(sum(32<=b<127 or b in (9,10,13) for b in data)/max(1,len(data)),6),
            'raw_bytes_exported':False,'encryption_algorithm':'unverified'}


@dataclass
class PayloadStudyResult:
    source:str
    status:str='failed'
    source_stable:bool=False
    summary:dict=field(default_factory=dict)
    metadata:list=field(default_factory=list)
    samples:list=field(default_factory=list)
    assessment:dict=field(default_factory=dict)
    issues:list=field(default_factory=list)
    report_paths:dict=field(default_factory=dict)

    def overview(self):
        return {'source':self.source,'status':self.status,'source_stable':self.source_stable,
                'analysis_only':True,'content_decoded_as_messages':False,'message_count':None,
                'summary':self.summary,'assessment':self.assessment,'issues':self.issues,'report_paths':self.report_paths}

    def markdown(self):
        lines=['# RMFH 载荷与元信息分析','',f'来源：`{self.source}`','',
               f'阶段分析状态：{self.status}；来源稳定：{self.source_stable}。',
               '这是有界结构探测报告；没有生成真实聊天消息。','',
               '## 元信息','', '| 文件 | 读取字节 | 完整读取 | wire 投影兼容 | 顶层字段数 |',
               '|---|---:|---|---|---:|']
        for row in self.metadata:
            lines.append(f"| {Path(row['path']).name} | {row['sample_bytes']} | {row['complete']} | {row['wire_probe']['compatible']} | {len(row['wire_probe'].get('fields',[]))} |")
        lines += ['', '结构兼容只说明字段边界可以完整读完；没有 .proto/已验证 Schema 时，字段含义仍未确认。',
                  '报告不输出原始字符串、密钥材料或采样字节。带 wxroam 前缀的字段不是已确认的解密密钥。','',
                  '## 载荷取样','',f"文件头模式覆盖：{self.summary.get('patterns_sampled',0)}/{self.summary.get('patterns_total',0)}。",
                  f"消息包：{self.summary.get('chat_samples',0)}；同目录同名索引候选：{self.summary.get('index_samples',0)}。",
                  f"完整载荷样本：{self.summary.get('complete_samples',0)}；受单文件上限截取：{self.summary.get('truncated_samples',0)}。",
                  f"元信息和载荷实际读取：{self.summary.get('payload_metadata_bytes_read',0)} 字节；预算：{self.summary.get('budget_bytes',0)} 字节。",
                  '目录/文件头检查额外最多读取每文件 256 字节；每个被采样的容器另外检查 256 字节头尾。',
                  '消息包与索引的配对依据仅为目录和文件名相同，不能证明消息级对应。','',
                  '## 解码评估','',f"已成功解码登记编码流：{self.summary.get('decoded_streams',0)}。",
                  f"样本状态统计：{self.summary.get('decoder_codes',{})}。",'',self.assessment.get('conclusion',''),'',
                  '高熵、无压缩签名或 wire 探测失败，均不足以确认加密算法。',
                  'needs_key 仅由明确登记且声明需要密钥的解码器返回；当前真实备份没有登记加密投影。','',
                  '## 后续条件','']
        lines += ['- '+condition for condition in self.assessment.get('required_conditions',[])]
        if self.issues:
            lines += ['', '## 问题','']+['- '+i['message'] for i in self.issues[:100]]
        return '\n'.join(lines)+'\n'

    def save(self,directory):
        directory=Path(directory).expanduser().resolve()
        source=Path(self.source)
        roots=[source,*[d.parent for d in find_devices(source)]]
        if any(directory==r or r in directory.parents for r in roots):
            raise UnsupportedWeChatSource('载荷报告不能保存在原备份内部')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        bundle=directory/f'rmfh_payload_{stamp}_{uuid4().hex[:12]}'
        bundle.mkdir(parents=True,exist_ok=False)
        names=('metadata_report.json','payload_samples.json','decoder_assessment.json','summary.md')
        self.report_paths={name:str(bundle/name) for name in names}
        common={'source':self.source,'report_version':'1.0','status':self.status,'source_stable':self.source_stable,
                'analysis_only':True,'raw_samples_exported':False,'message_schema_verified':False}
        reports={'metadata_report.json':{**common,'report_format':'rmfh-metadata-wire','files':self.metadata},
                 'payload_samples.json':{**common,'report_format':'rmfh-payload-samples','summary':self.summary,'samples':self.samples},
                 'decoder_assessment.json':{**common,'report_format':'rmfh-decoder-assessment','summary':self.summary,'assessment':self.assessment,'issues':self.issues}}
        documents={name:json.dumps(data,ensure_ascii=False,indent=2)+'\n' for name,data in reports.items()}
        documents['summary.md']=self.markdown()
        for name,text in documents.items():
            target=bundle/name;temporary=target.with_suffix(target.suffix+'.tmp')
            with temporary.open('x',encoding='utf-8',newline='\n') as handle:
                handle.write(text);handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,target)
        return self.report_paths


class RMFHPayloadStudy:
    def __init__(self,source,*,samples_per_pattern=2,sample_bytes=65536,total_bytes=4*1024*1024):
        self.source=checked_path(source)
        if not self.source.is_dir(): raise ValueError('载荷阶段需要备份目录来源')
        if type(samples_per_pattern) is not int or not 1<=samples_per_pattern<=4 or type(sample_bytes) is not int or not 1<=sample_bytes<=65536:
            raise ValueError('每模式样本数须为 1–4，单文件字节上限为 1–65536')
        self.per_pattern,self.cap,self.total=samples_per_pattern,sample_bytes,total_bytes
        ReadBudget(total_bytes)
        self.registry=DecoderRegistry()

    def _sample(self,path,role,pattern,budget,pair=None):
        path=checked_path(path)
        if self.source not in path.parents:
            raise SamplingError('out_of_scope','样本不在来源目录内')
        head,tail,stamp=read_edges(path)
        container=_envelope_from_edges(path,head,tail,stamp)
        if container.header['prefix_hex']!=pattern:
            raise SamplingError('source_changed','样本文件头与选择时的模式不一致')
        data,complete=read_region(self.source,path,offset=container.payload.offset,length=container.payload.length,cap=self.cap,budget=budget)
        decoded=self.registry.decode(data,complete=complete)
        row={'path':path.relative_to(self.source).as_posix(),'role':role,'header_pattern':pattern,
             'payload_offset':container.payload.offset,'payload_bytes':container.payload.length,'sample_bytes':len(data),
             'complete':complete,'pair_candidate':pair,'byte_evidence':byte_evidence(data),
             'header_opaque_shape':byte_evidence(head[16:]),'footer_opaque_shape':byte_evidence(tail[4:]),
             'compression_signature_candidate':compression_signature(data),'text_shape':text_shape(data),
             'wire_probe':probe_wire(data,complete=complete),'decoder':decoded.summary()}
        if decoded.data is not None:
            row['decoded_wire_probe']=probe_wire(decoded.data)
            row['decoded_text_shape']=text_shape(decoded.data)
        return row

    def analyze(self):
        result=PayloadStudyResult(str(self.source));budget=ReadBudget(self.total)
        inventory=RMFHFormatAnalyzer(self.source).analyze()
        directory_stamps={}
        groups={};selected=set();patterns_done=set()
        try:
            if inventory.status not in {'success','partial'} or not inventory.inventory_complete or not inventory.source_stable:
                raise SamplingError('invalid_source','来源清单不完整、未知或不稳定')
            directory_stamps={self.source/row['path']:file_stamp(self.source/row['path']) for row in inventory.directories}
            for row in inventory.file_headers:
                if row['category']=='ChatPackage' and row['status']=='supported_envelope':
                    groups.setdefault(row['header']['prefix_hex'],[]).append(row)
                if row['category']=='metadata' and row['status']=='non_rmfh':
                    data,complete=read_region(self.source,self.source/row['path'],offset=0,length=row['bytes'],cap=self.cap,budget=budget)
                    result.metadata.append({'path':row['path'],'file_bytes':row['bytes'],'sample_bytes':len(data),
                                            'complete':complete,'wire_probe':probe_wire(data,complete=complete),
                                            'text_shape':text_shape(data),'byte_evidence':byte_evidence(data)})
            if not groups:
                raise SamplingError('no_chat_samples','没有已识别的 ChatPackage 外壳候选')
            by_path={r['path']:r for r in inventory.file_headers}
            for pattern,rows in sorted(groups.items()):
                for item in sorted(rows,key=lambda r:(r['bytes'],r['path']))[:self.per_pattern]:
                    path=self.source/item['path']
                    index=path.parent.parent/'Index'/path.name
                    pair=index.relative_to(self.source).as_posix()
                    try:
                        result.samples.append(self._sample(path,'ChatPackage',pattern,budget,pair if pair in by_path else None))
                        patterns_done.add(pattern)
                        if pair in by_path and pair not in selected:
                            selected.add(pair)
                            candidate=by_path[pair]
                            if candidate['status']!='supported_envelope':
                                result.issues.append({'code':'unsupported_index','message':'同名索引候选的外壳不受支持','path':pair})
                            else:
                                result.samples.append(self._sample(index,'Index',candidate['header']['prefix_hex'],budget,item['path']))
                    except (SamplingError,UnsupportedWeChatSource,OSError) as exc:
                        result.issues.append({'code':getattr(exc,'code','sample_failed'),'message':str(exc),'path':item['path']})
                        if getattr(exc,'code',None)=='source_changed': raise
            for row in inventory.files:
                current=(self.source/row['path']).stat()
                if (current.st_size,current.st_mtime_ns)!=(row['bytes'],row['mtime_ns']):
                    raise SamplingError('source_changed','来源文件在载荷分析期间变化')
            if any(file_stamp(path)!=stamp for path,stamp in directory_stamps.items()):
                raise SamplingError('source_changed','来源目录在载荷分析期间变化')
            result.source_stable=True
            result.status='partial' if result.issues or inventory.issues else 'success'
            result.issues.extend(inventory.issues)
        except (SamplingError,UnsupportedWeChatSource,OSError) as exc:
            result.status='failed';result.source_stable=False
            result.issues.append({'code':getattr(exc,'code','study_failed'),'message':str(exc)})
        codes=Counter(r['decoder']['code'] for r in result.samples)
        prefixes={}
        for row in result.samples:
            digest=row['byte_evidence']['prefix16_sha256']
            prefixes.setdefault(digest,[]).append(row['path'])
        result.summary={'patterns_total':len(groups),'patterns_sampled':len(patterns_done),'metadata_files':len(result.metadata),
                        'metadata_wire_compatible':sum(r['wire_probe']['compatible'] for r in result.metadata),
                        'chat_samples':sum(r['role']=='ChatPackage' for r in result.samples),'index_samples':sum(r['role']=='Index' for r in result.samples),
                        'complete_samples':sum(r['complete'] for r in result.samples),'truncated_samples':sum(not r['complete'] for r in result.samples),
                        'payload_metadata_bytes_read':budget.used,'budget_bytes':budget.limit,'sample_bytes_cap':self.cap,
                        'decoder_codes':dict(codes),'decoded_streams':codes['decoded'],
                        'repeated_prefix_groups':[{'sha256':digest,'files':paths} for digest,paths in prefixes.items() if len(paths)>1],
                        'media_payloads_sampled':0,'database_files_opened':0}
        decoded=codes['decoded']
        result.assessment={'encoding_status':'some_registered_streams_decoded' if decoded else 'unknown_encoding',
                           'encryption_algorithm':'unverified','verified_key_available':False,'wechat_encryption_profile_registered':False,
                           'message_schema_verified':False,'real_messages_recovered':0,
                           'conclusion':('部分登记编码流可以解码，仍不能把结果映射成真实聊天消息。' if decoded else '取样未确认可用的正文解码方法；没有恢复真实文本。'),
                           'required_conditions':['产生备份的微信版本及对应格式证据','如涉及加密：适用密钥、明确参数及认证解密方法','经验证的消息正文 Schema、账号、方向和时间映射'],
                           'limitations':['wire 投影兼容不证明 Protobuf Schema 或字段含义','取样只代表选定文件与前缀，不能推广到所有载荷','熵与签名不能单独证明加密或算法','不导出原始采样、字符串或密钥材料']}
        return result
