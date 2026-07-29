from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings


class SepidarConnector:
    """HTTP client for the company Sepidar MCP gateway (not Cursor-dependent)."""

    def __init__(self, settings: Settings) -> None:
        self.url = settings.sepidar_mcp_url.rstrip("/")
        self.token = settings.sepidar_mcp_token.strip()

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
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
                # Prefer tools/call get_my_access via JSON-RPC when gateway speaks MCP.
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "get_my_access", "arguments": {}},
                }
                resp = await client.post(self.url, headers=self._headers(), json=payload)
                if resp.status_code >= 400:
                    # Fallback: GET probe
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
                data = resp.json()
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
            return {"ok": True, "data": resp.json()}

    async def sample_sales_review(self, from_date: str, to_date: str) -> dict[str, Any]:
        return await self.call_tool(
            "get_sales_review",
            {"FromDate": from_date, "ToDate": to_date, "limit": 20},
        )


def _summarize(data: Any) -> Any:
    if isinstance(data, dict):
        keys = list(data.keys())[:12]
        return {"keys": keys}
    return str(data)[:200]
