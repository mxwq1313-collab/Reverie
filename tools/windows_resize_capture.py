"""Record an explicitly selected synthetic Tk window and verify decoded frames.

This is a diagnostic helper, never loaded by the desktop application. It refuses
hidden/minimized/zero-size targets and existing output paths. A recording is
ready only after FFmpeg has encoded its first frame, and is accepted only after
successful shutdown and a full variable-frame-rate decode.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from pathlib import Path
import re
import subprocess
import time


class WindowRecording:
    def __init__(self, hwnd: int, path: Path, *, fps: int = 120):
        self.hwnd = hwnd
        self.path = Path(path)
        self.fps = fps
        self.process = None
        self.log = None
        self.started = None
        self.user = ctypes.WinDLL('user32')
        for name in ('IsWindowVisible', 'IsIconic'):
            getattr(self.user, name).argtypes = [ctypes.c_void_p]
            getattr(self.user, name).restype = wintypes.BOOL
        self.user.GetClientRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
        self.user.GetClientRect.restype = wintypes.BOOL
        self.initial_size = None
        self.failure = None

    def target_size(self):
        if not self.user.IsWindowVisible(self.hwnd) or self.user.IsIconic(self.hwnd):
            raise RuntimeError('Recording target is hidden or minimized')
        rect = wintypes.RECT()
        if not self.user.GetClientRect(self.hwnd, ctypes.byref(rect)) or rect.right <= 0 or rect.bottom <= 0:
            raise RuntimeError('Recording target has no client pixels')
        return [rect.right, rect.bottom]

    def start(self):
        import imageio_ffmpeg
        if self.process is not None:
            raise RuntimeError('Recording already started')
        if self.path.exists():
            raise FileExistsError(self.path)
        self.initial_size = self.target_size()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path = self.path.with_suffix('.capture.txt')
        self.log = self.log_path.open('x', encoding='utf-8')
        self.executable = imageio_ffmpeg.get_ffmpeg_exe()
        self.started = time.monotonic()
        self.process = subprocess.Popen([
            self.executable, '-hide_banner', '-loglevel', 'warning', '-nostats',
            '-stats_period', '0.1', '-progress', 'pipe:1', '-n', '-f', 'gdigrab',
            '-framerate', str(self.fps), '-draw_mouse', '0', '-i', f'hwnd={self.hwnd}',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '0', '-threads', '2',
            '-pix_fmt', 'yuv444p', '-vsync', '0', str(self.path),
        ], stdin=subprocess.PIPE, stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)

    def ready(self):
        if self.process is None:
            raise RuntimeError('Recording has not started')
        self.target_size()
        if self.process.poll() is not None:
            raise RuntimeError(f'Recorder exited before readiness: {self.process.returncode}')
        text = self.log_path.read_text(encoding='utf-8', errors='replace')
        return (self.path.exists() and self.path.stat().st_size > 0
                and any(int(n) > 0 for n in re.findall(r'^frame=(\d+)\s*$', text, re.M)))

    def check_target(self):
        try:
            return self.target_size()
        except RuntimeError as error:
            self.failure = str(error)
            raise

    def stop(self, *, verify=True):
        if self.process is None:
            return {'passed': False, 'error': 'Recording not started'}
        process, self.process = self.process, None
        if process.poll() is None:
            try:
                process.stdin.write(b'q\n')
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
            self.failure = 'Recorder required termination'
        finally:
            process.stdin.close()
            self.log.close()
        result = dict(path=str(self.path), requested_fps=self.fps,
                      initial_client_size=self.initial_size, returncode=process.returncode,
                      elapsed_s=time.monotonic()-self.started, error=self.failure,
                      passed=False)
        if process.returncode != 0 or self.failure or not self.path.exists() or not self.path.stat().st_size:
            return result
        if not verify:
            return result
        return self.verify_video(result)

    def verify_video(self, result):
        decoded = subprocess.run([
            self.executable, '-v', 'error', '-i', str(self.path), '-vsync', '0',
            '-f', 'framemd5', '-'], capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW, timeout=90)
        self.path.with_suffix('.frames.md5').write_text(decoded.stdout, encoding='utf-8')
        frames = [line.split(',') for line in decoded.stdout.splitlines() if line and not line.startswith('#')]
        result.update(decode_returncode=decoded.returncode, decoded_frames=len(frames),
                      decode_error=decoded.stderr[-2000:])
        # framemd5 provides the stream's actual time base; do not infer fps from
        # the Matroska container's nominal rate or duplicate frames with vsync.
        base = re.search(r'^#tb 0: (\d+)/(\d+)', decoded.stdout, re.M)
        if frames and base:
            timebase = int(base[1])/int(base[2])
            result['video_duration_s'] = (int(frames[-1][2])+int(frames[-1][3])-int(frames[0][2]))*timebase
            result['effective_fps'] = len(frames)/result['video_duration_s']
            result['distinct_frame_hashes'] = len({line[-1].strip() for line in frames})
        result['passed'] = (decoded.returncode == 0 and len(frames) >= 2
                            and not result.get('error') and not result.get('queue_drops'))
        return result
