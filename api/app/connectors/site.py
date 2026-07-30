from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings


class MaahedSiteConnector:
    """maahed.ir admin connector.

    Admin login requires image captcha. Simple HTTP captcha endpoint often 500s,
    so login+OCR runs via Playwright helper (scripts/maahed_admin_login.js).
    """

    def __init__(self, settings: Settings) -> None:
        self.base = settings.maahed_site_base_url.rstrip("/")
        path = (settings.maahed_site_admin_login_path or "/admin-panel/login").strip()
        if not path.startswith("/"):
            path = "/" + path
        self.login_url = urljoin(self.base + "/", path.lstrip("/"))
        self.username = settings.maahed_site_username.strip()
        self.password = settings.maahed_site_password.strip()

    async def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if not self.username or not self.password:
            return {
                "source": "maahed_site",
                "ok": False,
                "configured": False,
                "freshness_label": "داده فروش سایت: credential تنظیم نشده",
                "detail": "MAAHED_SITE_USERNAME / MAAHED_SITE_PASSWORD را در env بگذارید",
                "login_url": self.login_url,
                "checked_at": checked_at,
            }

        try:
            result = _run_admin_login(self.username, self.password)
            if not result.get("ok"):
                return {
                    "source": "maahed_site",
                    "ok": False,
                    "configured": True,
                    "logged_in": False,
                    "freshness_label": "سایت: لاگین ادمین ناموفق",
                    "detail": result.get("detail", "login failed"),
                    "login_url": self.login_url,
                    "checked_at": checked_at,
                }
            return {
                "source": "maahed_site",
                "ok": True,
                "configured": True,
                "logged_in": True,
                "freshness_label": "داده سفارش سایت: از پنل ادمین (لاگین+OCR کپچا)",
                "detail": result.get("detail", "لاگین admin-panel موفق"),
                "login_url": self.login_url,
                "orders": {
                    "title": result.get("title"),
                    "url": result.get("url"),
                    "http_status": result.get("order_http"),
                    "counts": result.get("counts") or {},
                    "ok": True,
                },
                "checked_at": checked_at,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "maahed_site",
                "ok": False,
                "configured": True,
                "freshness_label": "سایت: خطا در اتصال",
                "detail": str(exc),
                "login_url": self.login_url,
                "checked_at": checked_at,
            }

    async def sample_public_snapshot(self) -> dict[str, Any]:
        if self.username and self.password:
            result = _run_admin_login(self.username, self.password)
            if result.get("ok"):
                return {
                    "ok": True,
                    "authenticated": True,
                    "orders": result.get("counts") or {},
                    "title": result.get("title"),
                    "freshness_label": "داده فروش سایت: خلاصه سفارش از admin-panel",
                    "note": "لاگین با OCR کپچا (Playwright)",
                }

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(f"{self.base}/")
            resp.raise_for_status()
            titles = re.findall(r"<title>(.*?)</title>", resp.text, flags=re.I | re.S)
            return {
                "ok": True,
                "http_status": resp.status_code,
                "title": titles[0].strip() if titles else "",
                "note": "خواندن سفارش نیازمند لاگین admin-panel است؛ فعلاً وضعیت عمومی",
                "freshness_label": "داده فروش سایت: نمونه عمومی (نه سفارش)",
            }


def _run_admin_login(username: str, password: str) -> dict[str, Any]:
    script = _resolve_login_script()
    if script is None:
        return {
            "ok": False,
            "detail": "scripts/maahed_admin_login.js یافت نشد یا Playwright/node در دسترس نیست",
        }
    env = os.environ.copy()
    env["MAAHED_SITE_USERNAME"] = username
    env["MAAHED_SITE_PASSWORD"] = password
    proc = subprocess.run(
        ["node", str(script)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        check=False,
    )
    raw = (proc.stdout or "").strip().splitlines()
    if not raw:
        return {
            "ok": False,
            "detail": f"login helper empty stdout stderr={proc.stderr[-500:]}",
        }
    try:
        return json.loads(raw[-1])
    except json.JSONDecodeError:
        return {
            "ok": False,
            "detail": f"login helper bad json: {raw[-1][:300]} stderr={proc.stderr[-300:]}",
        }


def _resolve_login_script() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "scripts" / "maahed_admin_login.js",
        here.parents[2] / "scripts" / "maahed_admin_login.js",
        Path("/app/scripts/maahed_admin_login.js"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return None
