"""Sample only this process's GUI thread; never suspend an unrelated process."""
import collections
import ctypes as c
import threading
import time


class NativeSampler:
    def __init__(self):
        # Preserve the GIL while briefly suspending: the target cannot own it.
        self.k=c.PyDLL('kernel32',use_last_error=True);self.n=c.PyDLL('ntdll');self.dbg=c.WinDLL('dbghelp')
        self.k.GetCurrentProcess.restype=c.c_void_p;self.k.GetCurrentThreadId.restype=c.c_ulong
        self.process=self.k.GetCurrentProcess();self.tid=self.k.GetCurrentThreadId()
        self.k.OpenThread.argtypes=[c.c_ulong,c.c_int,c.c_ulong];self.k.OpenThread.restype=c.c_void_p
        self.handle=self.k.OpenThread(0x004A,0,self.tid)
        if not self.handle:raise OSError(c.get_last_error(),'OpenThread for own GUI thread')
        self.k.SuspendThread.argtypes=[c.c_void_p];self.k.SuspendThread.restype=c.c_ulong
        self.k.ResumeThread.argtypes=[c.c_void_p];self.k.ResumeThread.restype=c.c_ulong
        self.k.GetThreadContext.argtypes=[c.c_void_p,c.c_void_p];self.k.GetThreadContext.restype=c.c_int
        self.k.ReadProcessMemory.argtypes=[c.c_void_p,c.c_void_p,c.c_void_p,c.c_size_t,c.c_void_p];self.k.ReadProcessMemory.restype=c.c_int
        self.k.CloseHandle.argtypes=[c.c_void_p]
        self.n.RtlLookupFunctionEntry.argtypes=[c.c_uint64,c.POINTER(c.c_uint64),c.c_void_p];self.n.RtlLookupFunctionEntry.restype=c.c_void_p
        self.n.RtlVirtualUnwind.argtypes=[c.c_ulong,c.c_uint64,c.c_uint64,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p];self.n.RtlVirtualUnwind.restype=c.c_void_p
        self.stop=threading.Event();self.samples=[];self.errors=[];self.thread=None

    def loop(self):
        raw=c.create_string_buffer(1248);context=(c.addressof(raw)+15)&~15
        while not self.stop.wait(.005):
            frames=[]
            suspended=False
            try:
                c.c_uint32.from_address(context+48).value=0x10001F
                if self.k.SuspendThread(self.handle)==0xFFFFFFFF:continue
                suspended=True
                if not self.k.GetThreadContext(self.handle,context):continue
                for _ in range(48):
                    rip=c.c_uint64.from_address(context+248).value;rsp=c.c_uint64.from_address(context+152).value
                    if not rip or not rsp or frames and frames[-1]==rip:break
                    frames.append(rip);base=c.c_uint64()
                    entry=self.n.RtlLookupFunctionEntry(rip,c.byref(base),None)
                    if entry:
                        handler=c.c_void_p();establisher=c.c_uint64()
                        self.n.RtlVirtualUnwind(0,base.value,rip,entry,context,c.byref(handler),c.byref(establisher),None)
                    else:
                        ret=c.c_uint64();read=c.c_size_t()
                        if not self.k.ReadProcessMemory(self.process,rsp,c.byref(ret),8,c.byref(read)) or read.value!=8:break
                        c.c_uint64.from_address(context+248).value=ret.value;c.c_uint64.from_address(context+152).value=rsp+8
            except (OSError,ValueError) as error:self.errors.append(str(error))
            finally:
                if suspended:self.k.ResumeThread(self.handle)
            if frames:self.samples.append({'t_ns':time.perf_counter_ns()-self.started,'frames':frames})

    def start(self):
        self.started=time.perf_counter_ns();self.thread=threading.Thread(target=self.loop,daemon=True,name='own-gui-native-sampler');self.thread.start()

    def finish(self):
        self.stop.set()
        if self.thread:self.thread.join(3)
        class Symbol(c.Structure):
            _fields_=[('SizeOfStruct',c.c_ulong),('TypeIndex',c.c_ulong),('Reserved',c.c_uint64*2),('Index',c.c_ulong),('Size',c.c_ulong),('ModBase',c.c_uint64),('Flags',c.c_ulong),('Value',c.c_uint64),('Address',c.c_uint64),('Register',c.c_ulong),('Scope',c.c_ulong),('Tag',c.c_ulong),('NameLen',c.c_ulong),('MaxNameLen',c.c_ulong),('Name',c.c_char*1)]
        self.dbg.SymInitialize.argtypes=[c.c_void_p,c.c_char_p,c.c_int];self.dbg.SymInitialize.restype=c.c_int
        self.dbg.SymFromAddr.argtypes=[c.c_void_p,c.c_uint64,c.POINTER(c.c_uint64),c.c_void_p];self.dbg.SymFromAddr.restype=c.c_int
        self.dbg.SymGetModuleBase64.argtypes=[c.c_void_p,c.c_uint64];self.dbg.SymGetModuleBase64.restype=c.c_uint64
        self.dbg.SymCleanup.argtypes=[c.c_void_p]
        self.k.GetModuleFileNameW.argtypes=[c.c_void_p,c.c_wchar_p,c.c_ulong];self.k.GetModuleFileNameW.restype=c.c_ulong
        symbols={}
        initialized=self.dbg.SymInitialize(self.process,b".",True)
        try:
            for address in {a for sample in self.samples for a in sample['frames']}:
                buf=c.create_string_buffer(c.sizeof(Symbol)+1024);info=Symbol.from_buffer(buf);info.SizeOfStruct=c.sizeof(Symbol);info.MaxNameLen=1024;displacement=c.c_uint64()
                name=''
                if initialized and self.dbg.SymFromAddr(self.process,address,c.byref(displacement),buf):name=c.string_at(c.addressof(buf)+Symbol.Name.offset,info.NameLen).decode('utf-8',errors='replace')
                base=self.dbg.SymGetModuleBase64(self.process,address) if initialized else 0
                path=c.create_unicode_buffer(1024)
                if base:self.k.GetModuleFileNameW(base,path,1024)
                symbols[str(address)]={'module':path.value.rsplit('\\',1)[-1],'symbol':name,'displacement':displacement.value,'rva':address-base if base else None}
        finally:
            if initialized:self.dbg.SymCleanup(self.process)
            self.k.CloseHandle(self.handle)
        def label(address):
            value=symbols[str(address)];return value['module']+'!'+(value['symbol'] or hex(value['rva'] or address))
        leaves=collections.Counter(label(s['frames'][0]) for s in self.samples)
        return {'samples':self.samples,'symbols':symbols,'leaf_ranking':leaves.most_common(30),'errors':self.errors,'scope':'only own GUI thread; Windows exports/local symbols, no symbol download; wall-time samples, not CPU-only samples'}
