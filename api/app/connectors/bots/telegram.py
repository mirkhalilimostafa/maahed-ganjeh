from __future__ import annotations

from typing import Any

import httpx

from app.connectors.bots.base import BotAdapter, BotSendResult


class TelegramBot(BotAdapter):
    """Telegram Bot API: https://api.telegram.org/bot<token>/<method>"""

    channel = "telegram"

    def __init__(self, token: str, api_base: str = "https://api.telegram.org") -> None:
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self._me: dict[str, Any] | None = None

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    async def send_message(
        self,
        recipient: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> BotSendResult:
        chat_id = (recipient or "").strip()
        if not chat_id:
            return BotSendResult(
                ok=False,
                channel=self.channel,
                detail="برای تلگرام، recipient باید chat_id باشد",
            )
        body: dict[str, Any] = {"chat_id": _coerce_chat_id(chat_id), "text": message[:4096]}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._url("sendMessage"), json=body)
                data = resp.json()
                if resp.status_code >= 400 or not data.get("ok"):
                    return BotSendResult(
                        ok=False,
                        channel=self.channel,
                        detail=f"telegram sendMessage failed: {data}",
                    )
                mid = None
                result = data.get("result") or {}
                if isinstance(result, dict):
                    mid = str(result.get("message_id") or "")
                return BotSendResult(
                    ok=True,
                    channel=self.channel,
                    detail="پیام تلگرام ارسال شد",
                    message_id=mid or None,
                )
        except Exception as exc:  # noqa: BLE001
            return BotSendResult(ok=False, channel=self.channel, detail=str(exc))

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "ok": True,
            "configured": True,
            "mode": "telegram",
            "freshness_label": "بات تلگرام: فعال (ارسال واقعی)",
            "detail": "TelegramBot با توکن تنظیم‌شده",
            "bot": self._me,
            "api_base": self.api_base,
        }

    async def probe(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(self._url("getMe"))
            data = resp.json()
            if data.get("ok"):
                self._me = data.get("result")
            return data


def _coerce_chat_id(raw: str) -> int | str:
    s = raw.strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return s
