from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings


class SepidarConnector:
    """HTTP client for the company Sepidar MCP gateway (not Cursor-dependent)."""

    def __init__(self, settings: Settings) -> None:
        self.url = settings.sepidar_mcp_url.rstrip("/")
        token = settings.sepidar_mcp_token.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        self.token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if not self.token:
            return {
                "source": "sepidar",
                "ok": False,
                "configured": False,
                "freshness_label": "سپیدار: توکن تنظیم نشده",
                "detail": "SEPIDAR_MCP_TOKEN را در env سرور قرار دهید",
                "checked_at": checked_at,
            }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_my_access", "arguments": {}},
                }
                resp = await client.post(self.url, headers=self._headers(), json=payload)
                if resp.status_code >= 400:
                    probe = await client.get(self.url, headers=self._headers())
                    return {
                        "source": "sepidar",
                        "ok": probe.status_code < 500,
                        "configured": True,
                        "freshness_label": "داده مالی سپیدار: به‌روز لحظه‌ای (در صورت اتصال)",
                        "http_status": probe.status_code,
                        "detail": f"tools/call HTTP {resp.status_code}; GET probe {probe.status_code}",
                        "checked_at": checked_at,
                    }
                data = _unwrap_tool_payload(_parse_mcp_response(resp))
                return {
                    "source": "sepidar",
                    "ok": True,
                    "configured": True,
                    "freshness_label": "داده مالی سپیدار: به‌روز لحظه‌ای",
                    "detail": "اتصال MCP برقرار شد",
                    "raw_summary": _summarize(data),
                    "checked_at": checked_at,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "sepidar",
                "ok": False,
                "configured": True,
                "freshness_label": "سپیدار: خطا در اتصال",
                "detail": str(exc),
                "checked_at": checked_at,
            }

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token:
            return {"ok": False, "error": "SEPIDAR_MCP_TOKEN missing"}
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            raw = _parse_mcp_response(resp)
            return {"ok": True, "data": _unwrap_tool_payload(raw)}

    async def sample_sales_review(self, from_date: str, to_date: str) -> dict[str, Any]:
        return await self.call_tool(
            "get_sales_review",
            {"FromDate": from_date, "ToDate": to_date, "limit": 50},
        )

    async def sample_sales_items_review(self, from_date: str, to_date: str) -> dict[str, Any]:
        return await self.call_tool(
            "get_sales_items_review",
            {"FromDate": from_date, "ToDate": to_date, "limit": 50},
        )

    async def sample_bank_accounts(self) -> dict[str, Any]:
        return await self.call_tool("get_bank_accounts", {"limit": 20})


def _parse_mcp_response(resp: httpx.Response) -> Any:
    content_type = (resp.headers.get("content-type") or "").lower()
    text = resp.text.strip()
    if "text/event-stream" in content_type or text.startswith("event:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload:
                    return json.loads(payload)
        raise ValueError("empty SSE MCP response")
    return resp.json()


def _unwrap_tool_payload(data: Any) -> Any:
    """Flatten MCP tools/call envelopes to the actual tool result.

    Live gateway often returns: {jsonrpc, result:{content:[{type:'text', text:'...json...'}]}}
    """
    if not isinstance(data, dict):
        return data

    # jsonrpc tools/call wrapper
    if "result" in data and ("jsonrpc" in data or "id" in data):
        return _unwrap_tool_payload(data["result"])

    content = data.get("content")
    if isinstance(content, list) and content:
        texts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                texts.append(part["text"])
        if len(texts) == 1:
            return _maybe_json(texts[0])
        if texts:
            return [_maybe_json(t) for t in texts]
        return content

    if "structuredContent" in data:
        return data["structuredContent"]

    return data


def _maybe_json(text: str) -> Any:
    s = text.strip()
    if not s:
        return s
    if s[0] in "{[":
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return text
    return text


def _summarize(data: Any) -> Any:
    if isinstance(data, dict):
        keys = list(data.keys())[:12]
        return {"keys": keys}
    if isinstance(data, list):
        return {"type": "list", "len": len(data)}
    return str(data)[:200]
