"""Synthetic, offline lexical retrieval benchmark; never opens a user archive."""
import json
from pathlib import Path
import platform
import sqlite3
import statistics
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from wechat_archive import ChatService
from wechat_archive.agent import ArchiveScope
from wechat_archive.knowledge import KnowledgeSource
from wechat_archive.knowledge.index import KnowledgeIndex
from wechat_archive.knowledge.providers import LexicalEmbedding

PAIRS = [('晶界偏聚能','晶界偏聚能采用四能量计算'),('会议时间','会议时间定在周二下午三点'),
         ('备份目录','备份目录是本机资料文件夹'),('毕业论文','毕业论文需要补充误差分析'),
         ('咖啡馆','周末在咖啡馆见面'),('图例字号','图例字号统一设置为八磅'),
         ('差旅报销','差旅报销需要原始票据'),('实验温度','实验温度保持三百开尔文'),
         ('模型验证','模型验证使用独立测试集合'),('生日礼物','生日礼物准备一本书')]

def main():
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/'synthetic.db'
        service = ChatService(path)
        for i in range(2): service.create_user(wxid=f'benchmark_{i}',nickname=f'自建身份{i}')
        # Batch synthetic inserts avoid timing GUI/CRUD transaction overhead.
        with service.database.connection() as connection:
            from wechat_archive.database.hashing import message_hash
            for i in range(1000):
                text = PAIRS[i][1] if i<len(PAIRS) else f'演示消息第{i}条：日常天气、阅读、散步与生活记录。'
                stamp = '2026-10-14T00:00:00+00:00'
                connection.execute('INSERT INTO messages(sender_id,receiver_id,create_time,content,msg_type,source,message_hash) VALUES(?,?,?,?,?,?,?)',
                    (1,2,stamp,text,'text','manual',message_hash(1,2,stamp,text)))
        index = KnowledgeIndex(Path(folder)/'vectors.db',KnowledgeSource(ArchiveScope(path,1,2)),LexicalEmbedding())
        build = index.sync()
        timings=[]; cases=[]
        for _ in range(3):
            for expected,(query,_) in enumerate(PAIRS,1):
                start=time.perf_counter(); hits=index.search(query,limit=5)['hits']; timings.append((time.perf_counter()-start)*1000)
                if len(cases)<len(PAIRS):
                    ids=[h['chunk']['reference']['message']['message_id'] for h in hits]
                    cases.append({'query':query,'expected':expected,'ids':ids,'recall_at_5':expected in ids})
        timings.sort()
        result={'messages':1000,'queries':len(PAIRS),'runs':3,'kind':'lexical, not semantic',
                'recall_at_5':sum(c['recall_at_5'] for c in cases)/len(cases),
                'p50_ms':round(statistics.median(timings),3),'p95_ms':round(timings[int(len(timings)*.95)-1],3),
                'build_seconds':build['elapsed_seconds'],'index_bytes':index.path.stat().st_size,
                'platform':platform.platform(),'python':platform.python_version(),'sqlite':sqlite3.sqlite_version,'cases':cases}
        print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
