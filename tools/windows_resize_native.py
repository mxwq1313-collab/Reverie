"""Bounded native message/CPU/GDI instrumentation for our generated Tk window."""
import collections
import ctypes as c
import time


class NativeTrace:
    MESSAGES={5:'WM_SIZE',15:'WM_PAINT',20:'WM_ERASEBKGND',70:'WM_WINDOWPOSCHANGING',71:'WM_WINDOWPOSCHANGED',133:'WM_NCPAINT',134:'WM_NCACTIVATE',274:'WM_SYSCOMMAND',528:'WM_PARENTNOTIFY',562:'WM_EXITSIZEMOVE',561:'WM_ENTERSIZEMOVE'}
    def __init__(self,root,install_hooks=True):
        self.root=root;self.client=root.winfo_id();self.user=c.WinDLL('user32',use_last_error=True);self.kernel=c.WinDLL('kernel32',use_last_error=True);self.comctl=c.WinDLL('comctl32',use_last_error=True)
        self.kernel.GetCurrentThread.restype=c.c_void_p;self.kernel.GetCurrentProcess.restype=c.c_void_p
        self.thread=self.kernel.GetCurrentThread();self.process=self.kernel.GetCurrentProcess()
        self.kernel.GetThreadTimes.argtypes=[c.c_void_p,*([c.c_void_p]*4)];self.kernel.GetThreadTimes.restype=c.c_int
        self.kernel.GetProcessTimes.argtypes=[c.c_void_p,*([c.c_void_p]*4)];self.kernel.GetProcessTimes.restype=c.c_int
        self.kernel.QueryThreadCycleTime.argtypes=[c.c_void_p,c.POINTER(c.c_uint64)];self.kernel.QueryThreadCycleTime.restype=c.c_int
        self.user.GetGuiResources.argtypes=[c.c_void_p,c.c_ulong];self.user.GetGuiResources.restype=c.c_ulong
        self.user.GetParent.argtypes=[c.c_void_p];self.user.GetParent.restype=c.c_void_p
        self.user.IsWindow.argtypes=[c.c_void_p];self.user.IsWindow.restype=c.c_int
        self.kind=c.WINFUNCTYPE(c.c_ssize_t,c.c_void_p,c.c_uint,c.c_size_t,c.c_ssize_t,c.c_size_t,c.c_size_t)
        self.comctl.DefSubclassProc.argtypes=[c.c_void_p,c.c_uint,c.c_size_t,c.c_ssize_t];self.comctl.DefSubclassProc.restype=c.c_ssize_t
        self.comctl.SetWindowSubclass.argtypes=[c.c_void_p,self.kind,c.c_size_t,c.c_size_t];self.comctl.SetWindowSubclass.restype=c.c_int
        self.comctl.RemoveWindowSubclass.argtypes=[c.c_void_p,self.kind,c.c_size_t];self.comctl.RemoveWindowSubclass.restype=c.c_int
        self.events=[];self.targets={};self.errors=[];self.pulses=[];self.sizes=[];self.active=False;self.start_ns=time.perf_counter_ns();self.dropped=0
        self.callback=self.kind(self.dispatch)
        def visit(widget):
            if not widget.winfo_viewable():return
            hwnd=widget.winfo_id();self.targets[hwnd]={'path':str(widget),'class':widget.winfo_class(),'viewable_at_start':bool(widget.winfo_viewable())}
            for child in widget.winfo_children():visit(child)
        if install_hooks is True:visit(root)
        elif install_hooks:self.targets[self.client]={'path':str(root),'class':root.winfo_class(),'viewable_at_start':bool(root.winfo_viewable())}
        self.hwnd=self.user.GetParent(root.winfo_id());self.targets[self.hwnd]={'path':'<wrapper>','class':'TkTopLevel'}
        self.interactive_cpu=[];self.hooked=[]
        if install_hooks:
            for hwnd in self.targets:
                if not self.comctl.SetWindowSubclass(hwnd,self.callback,0x230,0):self.errors.append(['subclass',hwnd,c.get_last_error()])
                else:self.hooked.append(hwnd)

    def cpu_parts(self,process=False):
        values=[c.c_uint64() for _ in range(4)]
        fn=self.kernel.GetProcessTimes if process else self.kernel.GetThreadTimes
        if not fn(self.process if process else self.thread,*[c.byref(v) for v in values]):
            raise OSError(c.get_last_error(),'GetProcessTimes/GetThreadTimes')
        return values[2].value/10000,values[3].value/10000

    def cpu(self,process=False):return sum(self.cpu_parts(process))

    def cycles(self):
        value=c.c_uint64();self.kernel.QueryThreadCycleTime(self.thread,c.byref(value));return value.value

    def dispatch(self,hwnd,msg,wp,lp,identifier,reference):
        if self.active and hwnd==self.hwnd and msg in (561,562):
            kernel,user=self.cpu_parts()
            self.interactive_cpu.append({'message':self.MESSAGES[msg],'t_ns':time.perf_counter_ns()-self.start_ns,'kernel_ms':kernel,'user_ms':user})
        if self.active and hwnd==self.client and msg==5:self.sizes.append([time.perf_counter_ns()-self.start_ns,lp&0xffff,(lp>>16)&0xffff])
        track=self.active and msg in self.MESSAGES
        if track:begin=time.perf_counter_ns();cycles=self.cycles()
        result=self.comctl.DefSubclassProc(hwnd,msg,wp,lp)
        if track:
            elapsed=time.perf_counter_ns()-begin
            if len(self.events)<120000:self.events.append([begin-self.start_ns,elapsed,self.cycles()-cycles,int(hwnd),msg])
            else:self.dropped+=1
        return result

    def pulse(self):
        kernel,user=self.cpu_parts();process_kernel,process_user=self.cpu_parts(True)
        self.pulses.append({'t_ns':time.perf_counter_ns()-self.start_ns,'thread_cpu_ms':kernel+user,'thread_kernel_ms':kernel,'thread_user_ms':user,'process_cpu_ms':process_kernel+process_user,'process_kernel_ms':process_kernel,'process_user_ms':process_user,'gdi':self.user.GetGuiResources(self.process,0),'user':self.user.GetGuiResources(self.process,1),'width':self.root.winfo_width(),'height':self.root.winfo_height()})

    def start(self):
        self.start_ns=time.perf_counter_ns();self.events.clear();self.pulses.clear();self.interactive_cpu.clear();self.active=True;self.pulse()

    def finish(self):
        self.pulse();self.active=False
        groups=collections.defaultdict(lambda:[0,0,0,0])
        for start,wall,cycles,hwnd,msg in self.events:
            key=(self.targets.get(hwnd,{}).get('class','unknown'),self.MESSAGES[msg]);value=groups[key];value[0]+=1;value[1]+=wall/1e6;value[2]=max(value[2],wall/1e6);value[3]+=cycles
        ordered=[dict(widget_class=k[0],message=k[1],calls=v[0],inclusive_wall_ms=round(v[1],3),max_ms=round(v[2],3),thread_cycles=v[3]) for k,v in groups.items()]
        ordered.sort(key=lambda v:v['inclusive_wall_ms'],reverse=True)
        duration=(time.perf_counter_ns()-self.start_ns)/1e6
        return {'duration_ms':duration,'main_thread_cpu_ms':self.pulses[-1]['thread_cpu_ms']-self.pulses[0]['thread_cpu_ms'],'main_thread_kernel_ms':self.pulses[-1]['thread_kernel_ms']-self.pulses[0]['thread_kernel_ms'],'main_thread_user_ms':self.pulses[-1]['thread_user_ms']-self.pulses[0]['thread_user_ms'],'process_cpu_ms':self.pulses[-1]['process_cpu_ms']-self.pulses[0]['process_cpu_ms'],'interactive_cpu':self.interactive_cpu,'ranking':ordered,'events':self.events,'targets':self.targets,'pulses':self.pulses,'geometry':self.sizes,'errors':self.errors,'dropped':self.dropped,'scope':'only this generated-data process/window; message durations are inclusive, not additive'}

    def close(self):
        self.active=False
        for hwnd in self.hooked:
            if self.user.IsWindow(hwnd):self.comctl.RemoveWindowSubclass(hwnd,self.callback,0x230)
