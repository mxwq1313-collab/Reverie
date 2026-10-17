"""Windows-only generated-data native CPU/GDI/message/stack/recording probe.

No arbitrary target PID, private archive or GPU/system configuration changes.
Native hooks, sampling and capture have overhead: omit them for timing acceptance.
Keep a Computer Use selected foreground window, then create the --gate file.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--wgc-deps',type=Path,help='Use optional WGC/PyAV diagnostic dependencies from this isolated directory.')
parser.add_argument('--target',choices=['window','contacts','copilot','grip'],default='window')
parser.add_argument('--proxy-reference',action='store_true',help='Diagnostic reference: restore the previous native proxy-only split behavior.')
parser.add_argument('--scenario',choices=['empty','plain','forward','codex','memory'],default='plain')
parser.add_argument('--native-top',action='store_true',help='Only hook the Tk client and wrapper, reducing observer overhead.')
parser.add_argument('--batch-paint',action='store_true',help='Experimental native batching; not enabled in the application or accepted for release.')
parser.add_argument('--native',action='store_true');parser.add_argument('--record',action='store_true');parser.add_argument('--hold',action='store_true')
parser.add_argument('--sample',action='store_true')
parser.add_argument('--gate',type=Path)
parser.add_argument('--manual-start',action='store_true',help='Wait for F9 in the visible synthetic window before recording.')
parser.add_argument('--stop-gate',type=Path,help='End manual capture when this file appears.')
parser.add_argument('--seconds',type=int,default=60,choices=range(5,121),metavar='5..120')
args=parser.parse_args()
if sys.platform!='win32' or sys.maxsize<=2**32:parser.error('This probe requires 64-bit Windows Python.')
args.root=args.root.resolve();args.out.parent.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(args.root),str(args.root/'tests')]
from test_workbench import WorkbenchTests
case=WorkbenchTests();case.setUp();app=case.app;root=case.root
candidate=None;trace=None;record=None;sampler=None;class_restore=None
try:
    case.show(1500,860);root.attributes('-topmost',True);root.lift();root.focus_force();root.update();app.background_browsing=True
    if args.scenario=='empty':app.chat_text.set_rows([],app.owner_id)
    elif args.scenario=='plain':
        base=app.message_rows[0];rows=[{**base,'id':70000+i,'content':('长消息缩放验收，保留原文[微笑]。'*30+'\n'+str(i)),'msg_type':'text','attachments':[]} for i in range(100)]
        app.message_rows=rows;app.chat_text.set_rows_incremental(rows,app.owner_id)
    elif args.scenario=='forward':
        from test_release_211 import forward_xml
        base=app.message_rows[0];rows=[{**base,'id':71000+i,'content':forward_xml(10,True),'msg_type':'system','attachments':[]} for i in range(3)]
        app.message_rows=rows;app.chat_text.set_rows_incremental(rows,app.owner_id)
    elif args.scenario=='codex':
        panel=app.agent_panel;panel._clear()
        for i in range(14):panel._add('你' if i%2 else 'Codex · 回答',('## 合成回答\n\n- **归档依据**：自建测试内容。\n\n'*16)+str(i))
    else:app.show_page('随机回忆')
    def settle(seconds):root.after(round(seconds*1000),root.quit);root.mainloop()
    settle(2)
    if args.scenario=='forward':
        for value in app.chat_text.bubbles.values():value['forward'].toggle()
        settle(2)
    if args.batch_paint:
        from windows_paint_candidate import install
        candidate=install(root)
    if args.proxy_reference:
        app.browser_panes.configure(opaqueresize=False);app.workspace_panes.configure(opaqueresize=False)
    root.title('思绪 2.3 原生诊断 · 合成数据 · '+args.scenario)
    from windows_resize_native import NativeTrace
    trace=NativeTrace(root,install_hooks=True if args.native else 'top' if args.native_top else False)
    if args.sample:
        from windows_resize_stacks import NativeSampler
        sampler=NativeSampler()
    import ctypes
    api=ctypes.WinDLL('user32');api.GetParent.argtypes=[ctypes.c_void_p];api.GetParent.restype=ctypes.c_void_p
    hwnd=api.GetParent(root.winfo_id())
    api.GetForegroundWindow.restype=ctypes.c_void_p
    from ctypes import wintypes
    api.GetWindowRect.argtypes=[ctypes.c_void_p,ctypes.POINTER(wintypes.RECT)];rect=wintypes.RECT();api.GetWindowRect(hwnd,ctypes.byref(rect))
    api.SendMessageW.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t];api.SendMessageW.restype=ctypes.c_ssize_t
    hit=[]
    for dx in (0,1,7,8,9,rect.right-rect.left-9,rect.right-rect.left-2):
        x=rect.left+dx;y=(rect.top+rect.bottom)//2
        hit.append([dx,api.SendMessageW(hwnd,0x84,0,(y<<16)|(x&0xffff))])
    api.GetModuleHandleW=ctypes.WinDLL('kernel32').GetModuleHandleW
    api.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];api.GetModuleHandleW.restype=ctypes.c_void_p
    uia_before=bool(api.GetModuleHandleW('UIAutomationCore.dll'))
    foreground_start=api.GetForegroundWindow()==hwnd
    (args.out.with_suffix('.window.json')).write_text(json.dumps({'hwnd':hwnd,'title':root.title(),'pid':__import__('os').getpid(),'window_rect':[rect.left,rect.top,rect.right,rect.bottom],'horizontal_hit_test':hit,'synthetic_only':True}),encoding='utf-8')
    if args.manual_start:
        root.title('思绪 2.3 人工采集 · 请恢复窗口并按 F9 · 录制中后左右拖边约 10 秒')
        root.bind('<F9>',lambda event:root.quit())
        root.mainloop()
        root.unbind('<F9>')
    if args.gate:
        def ready():
            if args.gate.exists():root.quit()
            else:root.after(40,ready)
        root.after(40,ready);root.mainloop()
    root.geometry('1500x860+20+35');settle(.6)
    foreground_start=api.GetForegroundWindow()==hwnd
    internal_geometry=[];internal_foreground=[];last_internal=[None];motion_started=time.perf_counter_ns()
    def panel_pulse():
        values=[app.conversation_column.winfo_width(),app.message_content_column.winfo_width(),app.copilot_host.winfo_width()]
        if values!=last_internal[0]:
            internal_geometry.append([time.perf_counter_ns()-motion_started,*values]);internal_foreground.append(api.GetForegroundWindow()==hwnd);last_internal[0]=values
    if args.record:
        if args.wgc_deps:
            sys.path.insert(0,str(args.wgc_deps.resolve()))
            from windows_resize_wgc import WgcWindowRecording as WindowRecording
        else:
            from windows_resize_capture import WindowRecording
        record=WindowRecording(api.GetParent(root.winfo_id()),args.out.with_suffix('.mkv'))
        visible_deadline=time.monotonic()+120
        while True:
            try:record.target_size();break
            except RuntimeError:
                if time.monotonic()>=visible_deadline:raise
                root.title('思绪 2.3 等待恢复窗口 · 录制中后请拖内部区域分隔条')
                settle(.1)
        record.start()
        deadline=time.monotonic()+8
        while not record.ready():
            if time.monotonic()>=deadline:raise RuntimeError('Recorder did not encode its first frame within 8 seconds')
            settle(.08)
        root.title('思绪 2.3 录制中 · 请拖内部区域分隔条约 10 秒 · 完成后回消息 · '+args.scenario)
        if args.hold and args.wgc_deps:root.attributes('-topmost',False)
        args.out.with_suffix('.recording.json').write_text(json.dumps({'state':'ready','first_frame_verified':True,'hwnd':record.hwnd,'initial_client_size':record.initial_size,'synthetic_only':True}),encoding='utf-8')
    if args.hold:
        root.after(args.seconds*1000,root.quit)
        if trace:trace.start()
        if sampler:sampler.start()
        gaps=[];previous=[time.perf_counter()]
        def manual_pulse():
            now=time.perf_counter();gaps.append((now-previous[0])*1000);previous[0]=now
            if trace:trace.pulse()
            panel_pulse()
            if record:
                try:record.check_target()
                except RuntimeError:root.quit();return
            if args.stop_gate and args.stop_gate.exists():root.quit();return
            root.after(16,manual_pulse)
        root.after(16,manual_pulse);root.mainloop()
        result=trace.finish() if trace else {}
        result.update(heartbeat_interval_ms=16,heartbeat_p95_ms=sorted(gaps)[int(.95*len(gaps))] if gaps else None,heartbeat_max_ms=max(gaps,default=0))
    else:
        gaps=[];previous=[time.perf_counter()];active=[True]
        def pulse():
            now=time.perf_counter();gaps.append((now-previous[0])*1000);previous[0]=now
            if trace:trace.pulse()
            panel_pulse()
            if active[0]:root.after(8,pulse)
        sequence=[(w,700+round((w-980)*.3)) for w in range(980,1481,20)];sequence+=list(reversed(sequence))
        if args.target!='window':
            from types import SimpleNamespace
            pane=app.browser_panes if args.target=='contacts' else app.workspace_panes
            initial_sash=pane.sash_coord(0)[0]
            if args.target=='grip':app.start_copilot_drag(SimpleNamespace(x_root=600))
            else:pane.event_generate('<ButtonPress-1>',x=initial_sash+2,y=180)
        def step(i=0):
            if i==len(sequence):
                if args.target=='grip':app.finish_copilot_drag()
                elif args.target!='window':pane.event_generate('<ButtonRelease-1>',x=last_sash[0],y=180)
                root.after(800,root.quit);return
            w,h=sequence[i]
            if args.target=='window':root.geometry(f'{w}x{h}+20+35')
            elif args.target=='grip':app.drag_copilot(SimpleNamespace(x_root=600-round((w-980)*.45)))
            else:
                last_sash[0]=initial_sash+2+round((w-980)*(.3 if args.target=='contacts' else -.45))
                pane.event_generate('<B1-Motion>',x=last_sash[0],y=180,state=256)
            root.after(35,lambda:step(i+1))
        last_sash=[0]
        if trace:trace.start()
        if sampler:sampler.start()
        started=time.perf_counter();pulse();root.after(1,step);root.mainloop();active[0]=False
        result=trace.finish() if trace else {}
        result.update(scenario=args.scenario,sizes=len(sequence),elapsed_s=time.perf_counter()-started,p95_ms=sorted(gaps)[int(.95*len(gaps))],max_ms=max(gaps),over50=sum(v>50 for v in gaps),synthetic_only=True,tk_errors=[str(e) for e in case.errors])
    result['internal_geometry']=internal_geometry
    result['internal_geometry_foreground']=internal_foreground
    result['internal_geometry_clock_offset_from_trace_ns']=motion_started-trace.start_ns
    result['target']=args.target
    result['motion_evidence']={'outer_size_changes':len(trace.sizes),'internal_width_changes':max(0,len(internal_geometry)-1)}
    result.update(scenario=args.scenario,foreground_at_measurement_start=foreground_start,foreground_at_end=api.GetForegroundWindow()==hwnd,synthetic_only=True,tk_errors=[str(e) for e in case.errors])
    if candidate:
        result['native_paint_cumulative']={key:getattr(candidate,key) for key in ('batches','mutations','paints','post_failures')}
    result['ui_automation_module']={'before_foreground_gate':uia_before,'at_end':bool(api.GetModuleHandleW('UIAutomationCore.dll'))}
    result['final_layout']={'mode':app.copilot_mode,'expanded':app.copilot_expanded,'layout_job':app.layout_job,'root_width':root.winfo_width()}
    result['final_layout']['widgets']={name:{'x':getattr(app,name).winfo_x(),'width':getattr(app,name).winfo_width(),'mapped':bool(getattr(app,name).winfo_viewable())} for name in ('resize_viewport','workspace_panes','page_host','copilot_host')}
    assert not case.errors,case.errors
    if sampler:
        stack=sampler.finish();sampler=None
        args.out.with_suffix('.stacks.json').write_text(json.dumps(stack),encoding='utf-8');result['leaf_ranking']=stack['leaf_ranking'];result['native_samples']=len(stack['samples'])
    if record:
        result['recording']=record.stop();record=None
        args.out.with_suffix('.recording.json').write_text(json.dumps({'state':'finished','result':result['recording']}),encoding='utf-8')
    args.out.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','targets','pulses','ranking')},ensure_ascii=False)[:10000],flush=True)
finally:
    if candidate:candidate.close()
    if trace:trace.close()
    if record:
        recording_result=record.stop()
        args.out.with_suffix('.recording.json').write_text(json.dumps({'state':'failed_or_interrupted','result':recording_result}),encoding='utf-8')
    case.doCleanups()
