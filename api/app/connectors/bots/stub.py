from __future__ import annotations

from typing import Any

from app.connectors.bots.base import BotAdapter, BotSendResult


class StubBot(BotAdapter):
    """Phase-1 bot: logs outbound messages; no Telegram/Bale tokens required."""

    channel = "stub"

    def __init__(self) -> None:
        self._sent: list[dict[str, Any]] = []

    async def send_message(
        self,
        recipient: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> BotSendResult:
        entry = {
            "recipient": recipient,
            "message": message,
            "payload": payload or {},
        }
        self._sent.append(entry)
        return BotSendResult(
            ok=True,
            channel=self.channel,
            detail="پیام در StubBot ثبت شد (توکن بات هنوز تنظیم نشده)",
            message_id=str(len(self._sent)),
        )

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "ok": True,
            "configured": True,
            "mode": "stub",
            "sent_count": len(self._sent),
            "freshness_label": "بات: حالت Stub (بدون توکن واقعی)",
            "note": "توکن تلگرام/بله خالی است؛ پیام‌ها فقط لاگ می‌شوند",
            "detail": "StubBot فعال است",
        }

    @property
    def recent(self) -> list[dict[str, Any]]:
        return list(self._sent[-20:])
