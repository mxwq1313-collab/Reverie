
"""Synthetic mapped Tk/mainloop probe; no real archives or model calls."""
import argparse,json,sys,time,subprocess,platform,hashlib
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timedelta,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import tkinter as tk
from wechat_archive.ui.theme import Theme

def original(module,path):
    raw=subprocess.check_output(['git','show','678bfd3:'+path],cwd=ROOT)
    exec(compile(raw.decode('utf-8'),path,'exec'),module.__dict__)
    module._ui_lag_original_sha256=hashlib.sha256(raw).hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--case',choices=('all','agent','contacts','timeline','management'),default='all')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    import wechat_archive.ui.message_widgets as widgets
    import wechat_archive.ui.agent_panel as agent
    import wechat_archive.ui.rich_markdown as markdown
    import wechat_archive.ui.browser_panel as browser
    if args.baseline:
        for module,path in ((widgets,'wechat_archive/ui/message_widgets.py'),(agent,'wechat_archive/ui/agent_panel.py'),(markdown,'wechat_archive/ui/rich_markdown.py'),(browser,'wechat_archive/ui/browser_panel.py')):
            original(module,path)
    root=tk.Tk();root.geometry('1150x800+20+20');theme=Theme(root)
    errors=[];root.report_callback_exception=lambda *error:errors.append(str(error[1]))
    import PIL
    results={'baseline':args.baseline,'python':sys.version.split()[0],'tk':root.tk.call('info','patchlevel'),'pillow':PIL.__version__,
             'platform':platform.platform(),'processor':platform.processor(),'font':theme.body,'scale':theme.scale,'window':'1150x800','warmup_excluded_from_heartbeat':True,'cases':[]}
    modules=(widgets,agent,markdown,browser)
    results['source_ref']='678bfd3' if args.baseline else 'working_tree'
    results['source_fingerprints']={str(Path(module.__file__).relative_to(ROOT)).replace('\\','/'):
        module._ui_lag_original_sha256 if args.baseline else hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() for module in modules}
    app=SimpleNamespace(root=root,background_browsing=True,status=tk.StringVar(root),message_total=0,message_rows=[],loaded_offset=0,
                        current_page='聊天归档',thumbnail_service=SimpleNamespace(submit=lambda *a:None),update_message_count=lambda *a:None)
    def measure(name,start,done,timeout=45,start_delay=50,settle_ms=25):
        gaps=[];state={'begin':None,'last':None,'settled':None}
        def beat():
            now=time.perf_counter()
            if state['begin'] is not None and state['last'] is not None:gaps.append((now-state['last'])*1000)
            state['last']=now
            if state['begin'] is not None:
                if done():
                    if state['settled'] is None:state['settled']=now
                    if (now-state['settled'])*1000>=settle_ms:root.quit();return
                else:state['settled']=None
                if now-state['begin']>timeout:errors.append('timeout: '+name);root.quit();return
            state['job']=root.after(8,beat)
        def begin():
            state['begin']=state['last']=time.perf_counter();start()
        root.after(start_delay,begin);beat();root.mainloop()
        root.after_cancel(state['job'])
        record={'name':name,'wall_ms':round((time.perf_counter()-state['begin'])*1000,3),
                'heartbeat_max_ms':round(max(gaps,default=0),3),'heartbeat_p95_ms':round(sorted(gaps)[min(len(gaps)-1,int(len(gaps)*.95))],3)}
        results['cases'].append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
        if errors:raise RuntimeError(errors)
        return record
    if args.case in ('all','agent'):
        panel=agent.AgentPanel.__new__(agent.AgentPanel)
        panel.root=root;panel.app=SimpleNamespace(theme=theme);panel.transcript=tk.Text(root,wrap='word',font=theme.body);panel.transcript.pack(fill='both',expand=True)
        panel.messages=[];panel.by_id={};panel.follow_job=None;panel.closed=False
        panel.layout_dialogue=lambda:None;panel.queue_history=lambda:None;panel.jump_latest=lambda:panel.transcript.see('end')
        panel.open_reference=lambda number:None
        history=('## 历史\n含有 **重点** 和 [消息 #123] 的合成正文。\n- 一项\n\n'*1000)[:40000]
        state={'ready':False,'step':0,'costs':[]}
        def tick():
            panel.messages[-1]['text']+='新增 **文字** [消息 #123]。\n'
            t=time.perf_counter();panel._render();state['costs'].append((time.perf_counter()-t)*1000)
            state['step']+=1
            if state['step']<8:root.after(130,tick)
            else:state['ready']=True
        # Build history before the stream timing window.
        def prepare():
            panel.messages=[{'role':'Codex','text':history},{'role':'Codex','text':''}]
            panel._render();root.after(40,root.quit)
        root.after(1,prepare);root.mainloop()
        rec=measure('agent_40k_stream',tick,lambda:state['ready'])
        rec['render_p95_ms']=round(sorted(state['costs'])[int(len(state['costs'])*.95)],3)
        rec['render_max_ms']=round(max(state['costs']),3)
        t=time.perf_counter();panel.messages[-1]['role']='Codex · 回答';panel._render();rec['final_ms']=round((time.perf_counter()-t)*1000,3)
        if panel.follow_job:root.after_cancel(panel.follow_job)
        panel.transcript.destroy()
    if args.case in ('all','contacts'):
        from PIL import Image
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            avatars_folder=Path(folder)
            avatar_paths=[]
            for index in range(200):
                path=avatars_folder/f'avatar-{index}.png'
                Image.new('RGB',(256,256),(index*7%255,index*13%255,index*29%255)).save(path)
                avatar_paths.append(str(path))
            for n,avatars in ((200,False),(200,True),(500,False)):
                holder=tk.Frame(root);holder.place(x=0,y=0,width=320,height=740)
                view=widgets.ContactList(holder,theme,lambda:None);view.pack(fill='both',expand=True)
                rows=[dict(id=i,nickname=f'合成联系人{i:03d} 文字',message_count=i,avatar=avatar_paths[i] if avatars else None) for i in range(n)]
                measure(f'contacts_{n}_avatars_{avatars}',lambda:view.set_rows_incremental(rows,0),
                        lambda:not getattr(view,'rendering',False) and not getattr(view,'retired_widgets',{}) and not getattr(getattr(view,'avatar_service',None),'job',None))
                costs=[];label_updates=[];original_labels=view.update_labels
                def record_label(row,width):
                    value=original_labels(row,width)
                    if width==410:label_updates.append((str(row['id']),time.perf_counter()))
                    return value
                view.update_labels=record_label
                expected=set(getattr(view,'_mapped_cards',view.cards))
                for width in range(300,420,10):
                    t=time.perf_counter();last_resize=t;view.resize(SimpleNamespace(width=width));costs.append((time.perf_counter()-t)*1000)
                results['cases'][-1]['resize_callback_max_ms']=round(max(costs),3)
                rec=measure(f'contacts_{n}_labels_settle',lambda:None,lambda:not getattr(view,'label_job',None),start_delay=0,settle_ms=0)
                seen=set()
                for key,when in label_updates:
                    seen.add(key)
                    if expected.issubset(seen):
                        rec['labels_complete_ms']=round((when-last_resize)*1000,3);break
                view.update_labels=original_labels
                holder.destroy()
    if args.case in ('all','timeline'):
        texts=['今天把归档里的聊天重新整理了一遍，顺便核对了图片时间。','好，我晚点看看。','文字稍微长一点，用来模拟正常消息。'*4]
        base=datetime(2025,1,1,tzinfo=timezone.utc)
        def rows(n,offset=0):
            return [dict(id=i+1,sender_id=1 if i%2 else 2,sender_name='合成发送者',receiver_name='合成接收者',
                         create_time=(base+timedelta(minutes=i)).isoformat(),content=texts[i%3],msg_type='text',attachments=[])
                    for i in range(offset,n+offset)]
        for n in (100,300):
            holder=tk.Frame(root);holder.pack(fill='both',expand=True)
            view=widgets.BubbleTimeline(holder,theme);view.app=app;view.pack(fill='both',expand=True);app.message_total=n
            done=lambda:not any(getattr(view,x,None) for x in ('rendering','reflow_busy','layout_job','finish_job','layout_step_job','restore_job','stack_job')) and view.completed_layout is not None
            measure(f'timeline_{n}',lambda:view.set_rows_incremental(rows(n),1),done)
            if n==300:
                measure('timeline_append_100',lambda:view.set_rows_incremental(rows(100,300),1,append=True),done)
                times=[]
                for _ in range(30):
                    view.pending_anchor=None;t=time.perf_counter();view.refresh_visible();view.remember_scroll_anchor();times.append((time.perf_counter()-t)*1000)
                results['cases'][-1]['scroll_max_ms']=round(max(times),3)
            holder.destroy()
    if args.case in ('all','management'):
        from tkinter import ttk
        from wechat_archive.ui.browser_panel import BrowserMixin
        frame=ttk.Frame(root);frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,columns=('id','time','sender','receiver','content'),show='headings');tree.pack(fill='both',expand=True)
        owner=SimpleNamespace(root=root,message_tree=tree,message_rows=[dict(id=i,create_time='2025-01-01',sender_name='甲',receiver_name='乙',content='自建正文',msg_type='text',attachments=[]) for i in range(1000)],
                              current_page='工具与设置',current_subpage='数据管理',closed=False,background_browsing=True)
        owner.management_visible=lambda:True
        if hasattr(BrowserMixin,'refresh_management_messages'):
            owner.refresh_management_messages=lambda:BrowserMixin.refresh_management_messages(owner)
            measure('management_1000',lambda:BrowserMixin.sync_management_messages(owner),lambda:not getattr(owner,'management_job',None))
        else:measure('management_1000',lambda:BrowserMixin.sync_management_messages(owner),lambda:True)
        frame.destroy()
    results['errors']=errors;root.destroy()
    if args.output:args.output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
if __name__=='__main__':main()
