# -*- coding: utf-8 -*-
"""WeChat Windows WGC capture + chat-area detection.

Adapted from jev-chat-windows/app/capture.py (MIT), 2026.
Frames remain in memory and are never written to disk by this module.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time

import numpy as np

_IS_WINDOWS = sys.platform == "win32"
u32 = ctypes.windll.user32 if _IS_WINDOWS else None


def _require_windows() -> None:
    if not _IS_WINDOWS:
        raise RuntimeError("WeChat WGC capture is only available on Windows")


def find_wechat_hwnd() -> int:
    """Find the visible main WeChat window for Weixin.exe/WeChat.exe."""
    _require_windows()
    k32 = ctypes.windll.kernel32
    found: list[tuple[int, str]] = []

    def exe_of(pid: int) -> str:
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ""
        try:
            buf, size = ctypes.create_unicode_buffer(1024), ctypes.c_uint(1024)
            ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            return os.path.basename(buf.value).lower() if ok else ""
        finally:
            k32.CloseHandle(h)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        if not u32.IsWindowVisible(hwnd):
            return True
        pid = ctypes.c_ulong()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if exe_of(pid.value) in ("weixin.exe", "wechat.exe"):
            title = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(hwnd, title, 256)
            found.append((int(hwnd), title.value))
        return True

    u32.EnumWindows(cb, 0)
    if not found:
        raise RuntimeError("没找到 Weixin.exe / WeChat.exe 的可见窗口，微信开着吗？")
    return next((h for h, t in found if t == "微信"), found[0][0])


def unminimize(hwnd: int) -> bool:
    """Restore a minimized WeChat window without activation, then send it to bottom."""
    _require_windows()
    if not u32.IsIconic(hwnd):
        return False
    u32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    u32.SetWindowPos(hwnd, 1, 0, 0, 0, 0, 0x13)  # HWND_BOTTOM + no size/move/activate
    return True


def chat_area(full: np.ndarray, header_h: int = 60):
    """Locate (x0, y_top, x1, y_input, pane_bg, y_pane) from frame pixels."""
    H, W = full.shape[:2]
    if H < 120 or W < 200:
        return None
    right = full[::8, W // 2 :: 8].reshape(-1, 3)
    vals, cnt = np.unique(right, axis=0, return_counts=True)
    if not len(vals):
        return None
    bg = vals[cnt.argmax()]
    isbg = np.abs(full.astype(int) - bg).sum(-1) <= 6
    col = isbg[H // 4 : H * 3 // 4].mean(0)
    if not np.any(col > 0.3):
        return None
    x0 = int(np.argmax(col > 0.3))
    x1 = W - int(np.argmax(col[::-1] > 0.3))
    if x1 <= x0:
        return None
    row = isbg[:, x0:x1].mean(1)
    if not np.any(row > 0.9):
        return None
    y0 = int(np.argmax(row > 0.9))
    y1 = H - int(np.argmax(row[::-1] > 0.9))
    if y1 <= y0:
        return None
    band = full[y0:y1, x0:x1].astype(int)
    seps = y0 + np.where((band.std(axis=(1, 2)) < 4) & (row[y0:y1] < 0.1))[0]
    seps = [int(s) for i, s in enumerate(seps) if i == 0 or s - seps[i - 1] > 3]
    below = [s for s in seps if s > y0 + 0.45 * (y1 - y0)]
    y_in = below[0] if below else y1
    above = [s for s in seps if y0 + header_h < s < y_in - 50]
    y_top = above[-1] if above else y0 + header_h
    if x1 - x0 < 100 or y_in - y_top < 40:
        return None
    return x0, y_top, x1, y_in, bg, y0


class Capture:
    """Windows Graphics Capture watcher that returns only settled frames."""

    def __init__(self, hwnd: int, settle: float = 0.25, max_wait: float = 1.0):
        _require_windows()
        try:
            from windows_capture import WindowsCapture
        except ImportError as exc:
            raise RuntimeError(
                "缺少 windows-capture。请运行: pip install -e .[wechat-windows]"
            ) from exc
        self.settle, self.max_wait = settle, max_wait
        self.shape = self.area = self.last = self.pending = None
        self.t = self.t0 = 0.0
        cap = WindowsCapture(window_hwnd=hwnd)
        cap.event(self.on_frame_arrived)
        cap.event(self.on_closed)
        self.ctl = cap.start_free_threaded()

    def on_frame_arrived(self, frame, control):
        full = np.ascontiguousarray(frame.frame_buffer[:, :, :3][:, :, ::-1])
        if full.size == 0 or full.max() == 0:
            return
        if self.area is None or full.shape != self.shape:
            self.shape, self.area = full.shape, chat_area(full)
        if self.area is None:
            return
        x0, y0, x1, y1 = self.area[:4]
        chat = full[y0:y1, x0:x1]
        if self.last is not None and np.array_equal(chat, self.last):
            return
        self.last = chat
        if self.pending is None:
            self.t0 = time.perf_counter()
        self.pending, self.t = full, time.perf_counter()

    def on_closed(self):
        pass

    def settled(self):
        if self.pending is None:
            return None
        now = time.perf_counter()
        if now - self.t < self.settle and now - self.t0 < self.max_wait:
            return None
        full, self.pending = self.pending, None
        return full

    def alive(self) -> bool:
        return not self.ctl.is_finished()

    def stop(self) -> None:
        self.ctl.stop()

    def wait(self) -> None:
        self.ctl.wait()
