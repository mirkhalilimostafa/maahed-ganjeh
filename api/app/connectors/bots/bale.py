from __future__ import annotations

from typing import Any

import httpx

from app.connectors.bots.base import BotAdapter, BotSendResult


class BaleBot(BotAdapter):
    """Bale Bot API (Telegram-compatible): https://tapi.bale.ai/bot<token>/<method>"""

    channel = "bale"

    def __init__(self, token: str, api_base: str = "https://tapi.bale.ai") -> None:
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self._me: dict[str, Any] | None = None

    def _url(self, method: str) -> str:
        return f"{self.api_base}/bot{self.token}/{method}"

    def _file_url(self, file_path: str) -> str:
        path = (file_path or "").lstrip("/")
        return f"{self.api_base}/file/bot{self.token}/{path}"

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
                detail="برای بله، recipient باید chat_id عددی باشد (کاربر باید قبلاً به بات پیام داده باشد)",
            )
        body: dict[str, Any] = {"chat_id": _coerce_chat_id(chat_id), "text": message[:4096]}
        if payload and payload.get("dashboard_url"):
            # keep URL in text already; optional future inline keyboard
            pass
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._url("sendMessage"), json=body)
                data = resp.json()
                if resp.status_code >= 400 or not data.get("ok"):
                    return BotSendResult(
                        ok=False,
                        channel=self.channel,
                        detail=f"bale sendMessage failed: {data}",
                    )
                mid = None
                result = data.get("result") or {}
                if isinstance(result, dict):
                    mid = str(result.get("message_id") or "")
                return BotSendResult(
                    ok=True,
                    channel=self.channel,
                    detail="پیام بله ارسال شد",
                    message_id=mid or None,
                )
        except Exception as exc:  # noqa: BLE001
            return BotSendResult(ok=False, channel=self.channel, detail=str(exc))

    async def get_file(self, file_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self._url("getFile"), params={"file_id": file_id})
            data = resp.json()
            if resp.status_code >= 400 or not data.get("ok"):
                raise RuntimeError(f"bale getFile failed: {data}")
            return data.get("result") or {}

    async def download_file(self, file_path: str) -> bytes:
        url = self._file_url(file_path)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                raise RuntimeError(f"bale download failed: HTTP {resp.status_code}")
            return resp.content

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        timeout: int = 25,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if offset is not None:
            params["offset"] = offset
        async with httpx.AsyncClient(timeout=float(timeout) + 15.0) as client:
            resp = await client.get(self._url("getUpdates"), params=params)
            data = resp.json()
            if resp.status_code >= 400 or not data.get("ok"):
                raise RuntimeError(f"bale getUpdates failed: {data}")
            result = data.get("result") or []
            return result if isinstance(result, list) else []

    async def set_webhook(
        self,
        url: str,
        *,
        secret_token: str | None = None,
        drop_pending_updates: bool = False,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url, "drop_pending_updates": drop_pending_updates}
        if secret_token:
            body["secret_token"] = secret_token
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self._url("setWebhook"), json=body)
            data = resp.json()
            if resp.status_code >= 400 or not data.get("ok"):
                raise RuntimeError(f"bale setWebhook failed: {data}")
            return data

    async def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        body = {"drop_pending_updates": drop_pending_updates}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self._url("deleteWebhook"), json=body)
            data = resp.json()
            if resp.status_code >= 400 or not data.get("ok"):
                raise RuntimeError(f"bale deleteWebhook failed: {data}")
            return data

    async def get_webhook_info(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(self._url("getWebhookInfo"))
            data = resp.json()
            if resp.status_code >= 400 or not data.get("ok"):
                raise RuntimeError(f"bale getWebhookInfo failed: {data}")
            return data.get("result") or {}

    def status(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "ok": True,
            "configured": True,
            "mode": "bale",
            "freshness_label": "بات بله: فعال (ارسال واقعی)",
            "detail": "BaleBot با توکن تنظیم‌شده",
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
