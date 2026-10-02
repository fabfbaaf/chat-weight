# -*- coding: utf-8 -*-
"""RapidOCR message extraction for WeChat Windows.

Adapted from jev-chat-windows/app/ocr.py (MIT), 2026.
OCR consumes numpy arrays in memory; no screenshots are written to disk.
"""
from __future__ import annotations

import difflib
import re
import time

import numpy as np

_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError(
                "缺少 rapidocr-onnxruntime。请运行: pip install -e .[wechat-windows]"
            ) from exc
        _ENGINE = RapidOCR(
            intra_op_num_threads=4,
            det_limit_type="max",
            det_limit_side_len=4000,
        )
    return _ENGINE


def read_title(header: np.ndarray) -> str:
    res, _ = _engine()(header, use_cls=False)
    if not res:
        return ""
    first = min(res, key=lambda r: r[0][0][1])
    row = first[0][0][1] + (first[0][2][1] - first[0][0][1])
    text = min((r for r in res if r[0][0][1] < row), key=lambda r: r[0][0][0])[1]
    return re.sub(r"\s*[（(]\d+[)）]\s*$", "", text.strip())


def who_said(chat: np.ndarray, box):
    xs, ys = [p[0] for p in box], [p[1] for p in box]
    reg = chat[int(min(ys)) : int(max(ys)), int(min(xs)) : int(max(xs))].astype(int)
    if reg.size == 0:
        return None, None, 0
    vals, cnt = np.unique(reg.reshape(-1, 3), axis=0, return_counts=True)
    bg = vals[cnt.argmax()]
    if cnt.max() / reg.shape[0] / reg.shape[1] < 0.45:
        return None, bg, 0
    diff = np.abs(reg @ [0.299, 0.587, 0.114] - bg @ [0.299, 0.587, 0.114])
    ink_h = best = 0
    for r in (diff > 60).any(axis=1):
        best = best + 1 if r else 0
        ink_h = max(ink_h, best)
    if bg[1] > bg[0] + 40 and bg[1] > bg[2] + 40:
        return "me", bg, ink_h
    return ("her" if diff.max() >= 150 else "gray"), bg, ink_h


def similar(a: str, b: str) -> bool:
    if a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.75:
        return True
    return len(a) == len(b) >= 3 and sum(x != y for x, y in zip(a, b)) <= 1


class Reader:
    """Per-conversation OCR + scroll dedupe state."""

    def __init__(self):
        self.ocr = _engine()
        self.lh = None
        self.seen: list[tuple[str, str | None, str]] = []
        self.last_boxes = []
        self.last_ms = 0
        self.primed = False

    def read(self, chat: np.ndarray, pane_bg):
        t0 = time.perf_counter()
        res, _ = self.ocr(chat, use_cls=False)
        self.last_ms = int((time.perf_counter() - t0) * 1000)
        self.last_boxes = []
        W = chat.shape[1]
        name, raw = None, []
        for box, text, _ in sorted(res or [], key=lambda r: r[0][0][1]):
            kind, bg, h = who_said(chat, box)
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            rect = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
            if kind == "gray":
                on_pane = np.abs(bg - pane_bg).sum() <= 6
                taken = bool(
                    on_pane
                    and box[0][0] < 0.25 * W
                    and len(text) <= 16
                    and not re.search("[:：]", text)
                )
                if taken:
                    name = text
                self.last_boxes.append(rect + ("name" if taken else "gray", text))
                continue
            if kind is None or (self.lh and h < 0.6 * self.lh):
                self.last_boxes.append(rect + ("image" if kind is None else "tiny", text))
                continue
            self.last_boxes.append(rect + (kind, text))
            raw.append((kind, name if kind == "her" else None, text, box[0][1], box[2][1], h))
        if not self.lh and len(raw) >= 3:
            self.lh = float(np.median([r[5] for r in raw]))

        lines = []
        for who, nm, text, top, bottom, h in raw:
            if (
                lines
                and lines[-1][0] == who
                and lines[-1][1] == nm
                and top - lines[-1][4] < 0.6 * (self.lh or h)
            ):
                lines[-1][2] += text
                lines[-1][4] = bottom
            else:
                lines.append([who, nm, text, top, bottom])
        return [(w, n, t, y) for w, n, t, y, _ in lines]

    def prime(self, lines) -> None:
        """Mark the currently visible lines as seen without emitting them.

        ChatWeight intentionally does this on the first frame after start/switch so
        restarting the recorder does not re-insert the visible history as 'new'.
        """
        for w, n, t, _ in lines:
            if not self._seen(w, n, t):
                self.seen.append((w, n, t))
        del self.seen[:-500]
        self.primed = True

    def new_lines(self, lines, *, prime_first: bool = True):
        if prime_first and not self.primed:
            self.prime(lines)
            return []
        self.primed = True
        known_y = [y for w, n, t, y in lines if self._seen(w, n, t)]
        floor = max(known_y) if known_y else -1
        new = [(w, n, t) for w, n, t, y in lines if y > floor and not self._seen(w, n, t)]
        self.seen.extend((w, n, t) for w, n, t, _ in lines if not self._seen(w, n, t))
        del self.seen[:-500]
        return new

    def _seen(self, who: str, name: str | None, text: str) -> bool:
        return any(w == who and similar(t, text) for w, _, t in self.seen)
