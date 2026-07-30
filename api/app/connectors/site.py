from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings


class MaahedSiteConnector:
    """Session client for maahed.ir admin panel (Yii2 advanced-admin).

    Login URL: /admin-panel/login — requires CSRF (_csrf-admin) and usually captcha.
    """

    def __init__(self, settings: Settings) -> None:
        self.base = settings.maahed_site_base_url.rstrip("/")
        path = (settings.maahed_site_admin_login_path or "/admin-panel/login").strip()
        if not path.startswith("/"):
            path = "/" + path
        self.login_url = urljoin(self.base + "/", path.lstrip("/"))
        self.username = settings.maahed_site_username.strip()
        self.password = settings.maahed_site_password.strip()
        self.captcha = settings.maahed_site_captcha.strip()

    async def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        if not self.username or not self.password:
            return {
                "source": "maahed_site",
                "ok": False,
                "configured": False,
                "freshness_label": "داده فروش سایت: credential تنظیم نشده",
                "detail": "MAAHED_SITE_USERNAME / MAAHED_SITE_PASSWORD را در env بگذارید (لاگین: /admin-panel/login)",
                "login_url": self.login_url,
                "checked_at": checked_at,
            }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                home = await client.get(f"{self.base}/")
                login_page = await client.get(self.login_url)
                csrf = _extract_csrf(login_page.text)
                needs_captcha = _login_requires_captcha(login_page.text)

                if needs_captcha and not self.captcha:
                    return {
                        "source": "maahed_site",
                        "ok": False,
                        "configured": True,
                        "logged_in": False,
                        "freshness_label": "سایت: لاگین ادمین نیازمند کپچا است",
                        "detail": (
                            "فرم /admin-panel/login کپچا دارد؛ برای اتصال خودکار یا کپچا را "
                            "برای حساب سرویس غیرفعال کنید، یا API/توکن بدون کپچا بدهید"
                        ),
                        "login_url": self.login_url,
                        "captcha_required": True,
                        "home_http_status": home.status_code,
                        "checked_at": checked_at,
                    }

                form: dict[str, str] = {
                    "LoginForm[username]": self.username,
                    "LoginForm[password]": self.password,
                    "LoginForm[rememberMe]": "0",
                    "login-button": "1",
                }
                if csrf:
                    form["_csrf-admin"] = csrf
                if self.captcha:
                    form["LoginForm[captcha]"] = self.captcha

                login_resp = await client.post(self.login_url, data=form)
                logged_in = _looks_logged_in(login_resp)

                admin_home = await client.get(f"{self.base}/admin-panel/")
                admin_ok = admin_home.status_code < 400 and "login" not in str(admin_home.url).lower()

                ok = logged_in and admin_ok
                freshness = (
                    "داده فروش/سفارش سایت: پس از لاگین ادمین — تازگی وابسته به پنل"
                    if ok
                    else "سایت در دسترس است؛ لاگین ادمین ناموفق یا محدود"
                )
                return {
                    "source": "maahed_site",
                    "ok": ok,
                    "configured": True,
                    "logged_in": logged_in,
                    "admin_reachable": admin_ok,
                    "admin_http_status": admin_home.status_code,
                    "freshness_label": freshness,
                    "detail": (
                        "لاگین admin-panel موفق"
                        if ok
                        else (
                            f"لاگین admin-panel مبهم (HTTP {login_resp.status_code}); "
                            f"final_url={login_resp.url}; خانه={home.status_code}"
                        )
                    ),
                    "login_url": self.login_url,
                    "platform_hint": "Yii2 admin (_csrf-admin + captcha)",
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
        """Best-effort public read until authenticated order endpoints are wired."""
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(f"{self.base}/")
            resp.raise_for_status()
            titles = re.findall(r"<title>(.*?)</title>", resp.text, flags=re.I | re.S)
            return {
                "ok": True,
                "http_status": resp.status_code,
                "title": titles[0].strip() if titles else "",
                "note": "خواندن سفارش نیازمند لاگین /admin-panel است؛ فعلاً وضعیت عمومی سایت",
                "freshness_label": "داده فروش سایت: نمونه عمومی (نه سفارش)",
            }


def _extract_csrf(html: str) -> str | None:
    m = re.search(r'name="csrf-param"\s+content="([^"]+)"', html)
    param = m.group(1) if m else "_csrf-admin"
    m = re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
    if m:
        return m.group(1)
    m = re.search(rf'name="{re.escape(param)}"\s+value="([^"]+)"', html)
    return m.group(1) if m else None


def _login_requires_captcha(html: str) -> bool:
    return "LoginForm[captcha]" in html or "loginform-captcha" in html.lower()


def _looks_logged_in(resp: httpx.Response) -> bool:
    url = str(resp.url).lower()
    if "login" in url:
        return False
    body = resp.text.lower()
    if "logout" in body or "خروج" in resp.text:
        return True
    if resp.status_code == 200 and "admin-panel" in url and "login" not in url:
        return True
    return False
