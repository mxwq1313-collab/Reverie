"""Optional WGC diagnostic capture of our synthetic HWND, with lossless VFR RGB.

Install windows-capture==2.0.0 and av==16.0.1 in an isolated diagnostic directory.
It is never imported by the application or packaging. WGC arrival timestamps
are retained alongside its native timestamps; queue drops make validation fail.
Frames are padded, never scaled, and only the selected window is acquired.
"""
from fractions import Fraction
import json
from pathlib import Path
import queue
import threading
import time
import imageio_ffmpeg
from tools.windows_resize_capture import WindowRecording


class WgcWindowRecording(WindowRecording):
    def start(self):
        from windows_capture import WindowsCapture
        if self.path.exists():raise FileExistsError(self.path)
        self.initial_size=self.target_size()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.started=time.monotonic()
        self.executable=imageio_ffmpeg.get_ffmpeg_exe()
        self.encoded=threading.Event();self.stopping=False;self.frames=[];self.dropped=0
        self.items=queue.Queue(maxsize=12)
        self.writer=threading.Thread(target=self.encode,name='synthetic-wgc-encoder',daemon=True)
        self.writer.start()
        capture=WindowsCapture(cursor_capture=False,draw_border=None,minimum_update_interval=8,window_hwnd=self.hwnd)
        @capture.event
        def on_frame_arrived(frame,control):
            if self.stopping:return
            item=(time.perf_counter_ns(),int(frame.timespan),frame.frame_buffer.copy())
            try:self.items.put_nowait(item)
            except queue.Full:self.dropped+=1
        @capture.event
        def on_closed():
            if not self.stopping:self.failure='Capture target closed before stop'
        self.capture=capture;self.control=capture.start_free_threaded()

    def encode(self):
        import av
        import numpy as np
        container=None
        try:
            # Include possible maximization without scaling the original pixels.
            width=max(self.user.GetSystemMetrics(0),self.initial_size[0]+32)
            height=max(self.user.GetSystemMetrics(1),self.initial_size[1]+64)
            container=av.open(str(self.path),'w',options={'flush_packets':'1'})
            stream=container.add_stream('libx264rgb',rate=120)
            stream.width=width;stream.height=height;stream.pix_fmt='bgr24'
            stream.time_base=Fraction(1,1_000_000)
            stream.codec_context.time_base=Fraction(1,1_000_000)
            stream.options={'preset':'ultrafast','crf':'0','tune':'zerolatency','threads':'2'}
            base=None
            while True:
                item=self.items.get()
                if item is None:break
                arrival,native,array=item
                if base is None:base=arrival
                h,w=array.shape[:2]
                if w>width or h>height:
                    self.failure='Capture exceeded the unscaled recording canvas';continue
                canvas=np.zeros((height,width,4),dtype=np.uint8)
                canvas[:h,:w,:]=array
                frame=av.VideoFrame.from_ndarray(canvas,format='bgra')
                frame.pts=(arrival-base)//1000;frame.time_base=Fraction(1,1_000_000)
                for packet in stream.encode(frame):container.mux(packet)
                self.frames.append({'arrival_ns':arrival-base,'native_timespan':native,'width':w,'height':h})
                self.encoded.set()
            for packet in stream.encode():container.mux(packet)
        except Exception as error:
            self.failure=f'{type(error).__name__}: {error}'
        finally:
            if container:container.close()

    def ready(self):
        self.target_size()
        if self.failure:raise RuntimeError(self.failure)
        return self.encoded.is_set()

    def stop(self,*,verify=True):
        if not hasattr(self,'control'):
            return {'passed':False,'error':'WGC not started'}
        if self.stopping:return {'passed':False,'error':'Already stopped'}
        self.stopping=True
        try:self.control.stop()
        except Exception as error:self.failure=f'Capture stop failed: {error}'
        if self.writer.is_alive():
            try:self.items.put(None,timeout=10)
            except queue.Full:self.failure='Encoder queue did not drain'
        self.writer.join(timeout=30)
        if self.writer.is_alive():self.failure='Encoder did not drain within 30 seconds'
        result=dict(path=str(self.path),backend='Windows.Graphics.Capture',codec='libx264rgb lossless',
                    initial_client_size=self.initial_size,requested_min_interval_ms=8,
                    captured_frames=len(self.frames),queue_drops=self.dropped,error=self.failure,
                    elapsed_s=time.monotonic()-self.started,passed=False,
                    timing='VFR from frame arrival clock; native capture timestamps retained separately; padding outside content is not app UI')
        self.path.with_suffix('.wgc_frames.json').write_text(json.dumps(self.frames),encoding='utf-8')
        if self.frames:
            result['capture_duration_s']=self.frames[-1]['arrival_ns']/1e9
            if result['capture_duration_s']>0:result['capture_update_rate']=len(self.frames)/result['capture_duration_s']
        if not verify or not self.path.exists() or not self.path.stat().st_size:return result
        return self.verify_video(result)
