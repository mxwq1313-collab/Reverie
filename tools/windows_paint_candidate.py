"""Coalesce Tk child-window invalidation on Windows without hiding widgets.

EXPERIMENTAL ONLY: manual validation found visual defects. The application
does not install this hook. Moving a parent also needs descendant repaint;
this diagnostic version is retained for reproducing the failed candidate.
See docs/SIXU_2_3_0_READINESS.md before using --batch-paint.

MoveWindow(TRUE) calls UpdateWindow synchronously. Tk can move several native
children while completing one layout. SWP_NOREDRAW prevents those intermediate
native repaints; one posted message invalidates the changed children and their
exposed parents after the current native call returns. There is no trailing
resize timer, snapshot, forced UpdateWindow or hardware setting change.

IMPORTANT: the ctypes window procedure must never call Tk or schedule Tcl work.
All Tk bindings run in ordinary Tk callbacks; the native procedure uses Win32
only. Calling Tk here can corrupt _tkinter's saved thread state on Windows.
"""
from __future__ import annotations
import ctypes as c
import logging
import sys
import tkinter as tk


class _WindowPos(c.Structure):
    _fields_ = [('hwnd', c.c_void_p), ('after', c.c_void_p),
                ('x', c.c_int), ('y', c.c_int), ('width', c.c_int),
                ('height', c.c_int), ('flags', c.c_uint)]


class NativePaintBatch:
    def __init__(self, root):
        self.root = root
        self.closed = False
        self.pending = set()
        self.windows = set()
        self.posted = False
        self.batches = self.mutations = self.paints = self.post_failures = 0
        self.user = c.WinDLL('user32', use_last_error=True)
        self.com = c.WinDLL('comctl32', use_last_error=True)
        self.kind = c.WINFUNCTYPE(c.c_ssize_t, c.c_void_p, c.c_uint,
                                 c.c_size_t, c.c_ssize_t, c.c_size_t, c.c_size_t)
        self.user.GetParent.argtypes = [c.c_void_p]
        self.user.GetParent.restype = c.c_void_p
        self.user.IsWindow.argtypes = [c.c_void_p]
        self.user.IsWindow.restype = c.c_int
        self.user.InvalidateRect.argtypes = [c.c_void_p, c.c_void_p, c.c_int]
        self.user.InvalidateRect.restype = c.c_int
        self.user.RegisterWindowMessageW.argtypes = [c.c_wchar_p]
        self.user.RegisterWindowMessageW.restype = c.c_uint
        self.user.PostMessageW.argtypes = [c.c_void_p, c.c_uint, c.c_size_t, c.c_ssize_t]
        self.user.PostMessageW.restype = c.c_int
        self.com.DefSubclassProc.argtypes = [c.c_void_p, c.c_uint, c.c_size_t, c.c_ssize_t]
        self.com.DefSubclassProc.restype = c.c_ssize_t
        self.com.SetWindowSubclass.argtypes = [c.c_void_p, self.kind, c.c_size_t, c.c_size_t]
        self.com.SetWindowSubclass.restype = c.c_int
        self.com.RemoveWindowSubclass.argtypes = [c.c_void_p, self.kind, c.c_size_t]
        self.com.RemoveWindowSubclass.restype = c.c_int
        self.callback = self.kind(self._dispatch)
        self.identifier = id(self)
        self.message = self.user.RegisterWindowMessageW('ChatArchive.NativePaintBatch.Flush.1')
        self.wrapper = None
        if not self.message:
            raise OSError('Cannot register the native paint message')
        self.bindings = {
            '<Map>': root.bind('<Map>', self._mapped, add='+'),
            '<Destroy>': root.bind('<Destroy>', self._destroyed, add='+'),
        }
        self._visit(root)

    def _hook(self, hwnd):
        if hwnd in self.windows:
            return True
        if self.com.SetWindowSubclass(hwnd, self.callback, self.identifier, 0):
            self.windows.add(hwnd)
            return True
        return False

    def _ensure_wrapper(self):
        if self.wrapper:
            return True
        hwnd = self.user.GetParent(self.root.winfo_id())
        if hwnd and self._hook(hwnd):
            self.wrapper = hwnd
            return True
        return False

    def _visit(self, widget):
        if widget.winfo_toplevel() is not self.root or not widget.winfo_viewable():
            return
        if not self._ensure_wrapper():
            return
        self._hook(widget.winfo_id())
        for child in widget.winfo_children():
            self._visit(child)

    def _mapped(self, event):
        if not self.closed and isinstance(event.widget, tk.Misc):
            try:
                if event.widget.winfo_toplevel() is self.root and event.widget.winfo_viewable() and self._ensure_wrapper():
                    self._hook(event.widget.winfo_id())
            except tk.TclError:
                pass  # A queued Map may refer to a widget already destroyed.

    def _destroyed(self, event):
        if event.widget is self.root:
            self.close()

    def _dispatch(self, hwnd, message, wp, lp, identifier, reference):
        if message == 0x82:  # WM_NCDESTROY: do not retain reused HWND values.
            self.com.RemoveWindowSubclass(hwnd, self.callback, self.identifier)
            self.windows.discard(hwnd)
            self.pending.discard(hwnd)
            if hwnd == self.wrapper:
                self.wrapper = None
                self._flush()
        if not self.closed:
            if message == 15:
                self.paints += 1
            if hwnd == self.wrapper and message == self.message:
                self._flush()
                return 0
            if hwnd != self.wrapper and message == 70 and lp:
                position = _WindowPos.from_address(lp)
                if position.flags & 3 != 3:  # At least one of move/size changed.
                    position.flags |= 8  # SWP_NOREDRAW; preserve all other flags.
                    self.mutations += 1
        result = self.com.DefSubclassProc(hwnd, message, wp, lp)
        if not self.closed and hwnd != self.wrapper and message == 71 and lp:
            if _WindowPos.from_address(lp).flags & 3 != 3:
                self.pending.add(hwnd)
                parent = self.user.GetParent(hwnd)
                if parent:
                    self.pending.add(parent)
                if not self.posted:
                    self.posted = True
                    if not self.user.PostMessageW(self.wrapper, self.message, 0, 0):
                        self.post_failures += 1
                        self._flush()  # Fail back to immediate valid pixels.
        return result

    def _flush(self):
        self.posted = False
        pending, self.pending = self.pending, set()
        if pending:
            self.batches += 1
        for hwnd in pending:
            if self.user.IsWindow(hwnd):
                self.user.InvalidateRect(hwnd, None, False)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._flush()
        for sequence, binding in self.bindings.items():
            try:
                # Python 3.10 unbind(sequence, funcid) clears every callback.
                script = self.root.bind(sequence)
                kept = [line for line in script.splitlines() if '['+binding+' ' not in line]
                self.root.tk.call('bind', str(self.root), sequence, '\n'.join(kept))
                self.root.deletecommand(binding)
            except tk.TclError:
                pass
        for hwnd in tuple(self.windows):
            if self.user.IsWindow(hwnd):
                self.com.RemoveWindowSubclass(hwnd, self.callback, self.identifier)
        self.windows.clear()


def install(root):
    if sys.platform != 'win32':
        return None
    try:
        return NativePaintBatch(root)
    except OSError:
        logging.getLogger(__name__).exception('Native paint batching unavailable')
        return None
