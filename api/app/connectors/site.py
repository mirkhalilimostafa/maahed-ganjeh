from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings


class MaahedSiteConnector:
    """Session-based connector for maahed.ir (Yii2 storefront; admin may be IP-restricted)."""

    def __init__(self, settings: Settings) -> None:
        self.base = settings.maahed_site_base_url.rstrip("/")
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
                "checked_at": checked_at,
            }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                home = await client.get(f"{self.base}/")
                login_page = await client.get(f"{self.base}/site/login")
                csrf = _extract_csrf(login_page.text)
                form = {
                    "LoginForm[username]": self.username,
                    "LoginForm[password]": self.password,
                }
                if csrf:
                    form["_csrf-frontend"] = csrf

                login_resp = await client.post(f"{self.base}/site/login", data=form)
                logged_in = _looks_logged_in(login_resp)

                admin_probe = await client.get(f"{self.base}/admin")
                admin_ok = admin_probe.status_code < 400

                # Public catalog signal (orders need admin; catalog proves site reachability)
                catalog_ok = home.status_code == 200

                ok = logged_in or catalog_ok
                freshness = (
                    "داده فروش/مشتری سایت: تا ۵ روز تأخیر محتمل — نیاز به خواندن پنل پس از لاگین"
                    if logged_in
                    else "سایت در دسترس است؛ لاگین یا پنل ادمین محدود است"
                )
                return {
                    "source": "maahed_site",
                    "ok": ok,
                    "configured": True,
                    "logged_in": logged_in,
                    "admin_reachable": admin_ok,
                    "admin_http_status": admin_probe.status_code,
                    "freshness_label": freshness,
                    "detail": (
                        "لاگین storefront موفق"
                        if logged_in
                        else f"لاگین storefront مبهم (HTTP {login_resp.status_code}); خانه={home.status_code}"
                    ),
                    "platform_hint": "Yii2 (_csrf-frontend)",
                    "checked_at": checked_at,
                }
        except Exception as exc:  # noqa: BLE001
            return {
                "source": "maahed_site",
                "ok": False,
                "configured": True,
                "freshness_label": "سایت: خطا در اتصال",
                "detail": str(exc),
                "checked_at": checked_at,
            }

    async def sample_public_snapshot(self) -> dict[str, Any]:
        """Best-effort public read until dedicated order API is wired behind admin."""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(f"{self.base}/")
            resp.raise_for_status()
            titles = re.findall(r"<title>(.*?)</title>", resp.text, flags=re.I | re.S)
            return {
                "ok": True,
                "http_status": resp.status_code,
                "title": titles[0].strip() if titles else "",
                "note": "خواندن سفارش نیازمند دسترسی پنل ادمین است؛ فعلاً وضعیت عمومی سایت",
                "freshness_label": "داده فروش سایت: نمونه عمومی (نه سفارش)",
            }


def _extract_csrf(html: str) -> str | None:
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(r'name="_csrf-frontend"\s+value="([^"]+)"', html)
    return m.group(1) if m else None


def _looks_logged_in(resp: httpx.Response) -> bool:
    url = str(resp.url).lower()
    if "login" not in url and resp.status_code == 200:
        return True
    body = resp.text.lower()
    if "logout" in body or "خروج" in resp.text:
        return True
    # Failed login usually stays on /site/login with errors
    if "site/login" in url:
        return False
    return resp.status_code in (200, 302)
