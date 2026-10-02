# -*- coding: utf-8 -*-
"""Capture subprocess for live WeChat OCR.

Adapted from jev-chat-windows/app/worker.py (MIT), 2026.
This worker emits only plain tuples over multiprocessing.Queue.
"""
from __future__ import annotations

import ctypes
import sys
import time
import traceback

import numpy as np

from .capture import Capture, chat_area, unminimize
from .ocr import Reader, read_title, similar


def _err(q):
    q.put(("status", " ".join(traceback.format_exc().split())[-400:]))


def run(q, hwnd: int, enabled, prime_existing: bool = True):
    if sys.platform != "win32":
        q.put(("dead", "微信实时采集只能在 Windows 运行"))
        return
    ctypes.windll.user32.SetProcessDPIAware()
    cap = None
    readers: dict[str, Reader] = {}
    title, head = "", None
    warned = False

    while True:
        if not enabled.is_set():
            if cap is not None:
                cap.stop()
                cap = None
            q.put(("paused",))
            enabled.wait()
            continue

        if cap is None:
            try:
                cap = Capture(hwnd)
            except Exception as e:
                q.put(("dead", "无法开始采集：" + (" ".join(str(e).split())[:200] or type(e).__name__)))
                enabled.clear()
                continue
            q.put(("resumed",))

        if not cap.alive():
            break

        try:
            unminimize(hwnd)
            full = cap.settled()
            if full is not None:
                area = chat_area(full)
                if area is None:
                    if not warned:
                        q.put(("status", "消息区认不出来（窗口太小或微信布局正在变化）"))
                    warned = True
                else:
                    warned = False
                    cap.area = area
                    x0, y0, x1, y1, bg, y_pane = area
                    crop = full[y_pane:y0, x0:x1]
                    if head is None or not np.array_equal(crop, head):
                        head = crop.copy()
                        name = read_title(crop)
                        name = next((k for k in readers if similar(k, name)), name) if name else ""
                        name = name or title or "当前会话"
                        if name != title:
                            title = name
                            q.put(("chat", title))
                    reader = readers.setdefault(title, Reader())
                    lines = reader.read(full[y0:y1, x0:x1], bg)
                    new = reader.new_lines(lines, prime_first=prime_existing)
                    if new:
                        q.put(("lines", title, new, int(time.time() * 1000)))
        except Exception:
            _err(q)
        time.sleep(0.05)

    q.put(("dead", "采集停了（微信关闭或 WGC 会话结束）"))
    try:
        if cap is not None:
            cap.wait()
    except Exception:
        _err(q)
