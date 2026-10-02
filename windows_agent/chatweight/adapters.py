from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Platform, UnifiedMessage
from .wechat_live import WeChatLiveRecorder, WeChatSqliteIngestor


class ChatCaptureAdapter(ABC):
    platform: Platform

    @abstractmethod
    def capture(self) -> list[UnifiedMessage]:
        raise NotImplementedError


class WeChatWindowsAdapter(ChatCaptureAdapter):
    """Windows WeChat integration backed by Jev WGC + RapidOCR.

    Real-time use is provided by WeChatLiveRecorder. The one-shot capture method
    remains empty because WGC/OCR is event-driven and should not pretend to be a
    polling API.
    """

    platform = Platform.WECHAT

    def capture(self) -> list[UnifiedMessage]:
        return []

    @staticmethod
    def live_recorder(db_path, schema_path, *, prime_existing: bool = True) -> WeChatLiveRecorder:
        return WeChatLiveRecorder(db_path, schema_path, prime_existing=prime_existing)


class ImportAdapter(ChatCaptureAdapter):
    """Placeholder for future user-authorized history import."""

    platform = Platform.WECHAT

    def capture(self) -> list[UnifiedMessage]:
        return []


__all__ = [
    "ChatCaptureAdapter",
    "WeChatWindowsAdapter",
    "WeChatLiveRecorder",
    "WeChatSqliteIngestor",
    "ImportAdapter",
]
