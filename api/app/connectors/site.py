from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings

_SESSION_PATHS = [
    Path("/data/maahed_admin_session.json"),
    Path(__file__).resolve().parents[3] / "data" / "maahed_admin_session.json",
    Path("maahed_admin_session.json"),
]


class MaahedSiteConnector:
    """maahed.ir admin connector via httpx + digit OCR (no Playwright/Node in pod)."""

    def __init__(self, settings: Settings) -> None:
        self.base = settings.maahed_site_base_url.rstrip("/")
        path = (settings.maahed_site_admin_login_path or "/admin-panel/login").strip()
        if not path.startswith("/"):
            path = "/" + path
        self.login_url = urljoin(self.base + "/", path.lstrip("/"))
        self.username = settings.maahed_site_username.strip()
        self.password = settings.maahed_site_password.strip()
        self.static_captcha = settings.maahed_site_captcha.strip()

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
                "reason_code": "missing_credentials",
            }

        try:
            result = await _login_and_orders(
                self.base,
                self.login_url,
                self.username,
                self.password,
                static_captcha=self.static_captcha,
            )
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
                    "reason_code": result.get("reason_code", "login_failed"),
                }
            return {
                "source": "maahed_site",
                "ok": True,
                "configured": True,
                "logged_in": True,
                "freshness_label": "داده سفارش سایت: از پنل ادمین (httpx+OCR)",
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
                "via": result.get("via"),
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
                "reason_code": "exception",
            }

    async def sample_public_snapshot(self) -> dict[str, Any]:
        if self.username and self.password:
            result = await _login_and_orders(
                self.base,
                self.login_url,
                self.username,
                self.password,
                static_captcha=self.static_captcha,
            )
            if result.get("ok"):
                return {
                    "ok": True,
                    "authenticated": True,
                    "orders": result.get("counts") or {},
                    "title": result.get("title"),
                    "freshness_label": "داده فروش سایت: خلاصه سفارش از admin-panel",
                    "note": "لاگین httpx + OCR کپچا",
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


def _session_path() -> Path:
    for path in _SESSION_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue
    return Path("maahed_admin_session.json")


def _load_cookies() -> dict[str, str]:
    path = _session_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = data.get("cookies") or {}
        return {str(k): str(v) for k, v in cookies.items()} if isinstance(cookies, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cookies(cookies: dict[str, str]) -> None:
    path = _session_path()
    try:
        path.write_text(
            json.dumps(
                {"cookies": cookies, "saved_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass


def _ocr_digits(image_bytes: bytes) -> str:
    try:
        import ddddocr  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("ddddocr نصب نیست؛ pip install ddddocr") from exc
    ocr = ddddocr.DdddOcr(show_ad=False)
    raw = ocr.classification(image_bytes) or ""
    return re.sub(r"\D", "", str(raw))


def _extract_csrf(html: str) -> str:
    m = re.search(r'name="_csrf-admin"\s+value="([^"]+)"', html)
    if not m:
        m = re.search(r'csrf-token"\s+content="([^"]+)"', html)
    return m.group(1) if m else ""


def _parse_order_counts(body: str) -> dict[str, str | None]:
    def pick(label: str) -> str | None:
        m = re.search(label + r"\s*\n\s*([0-9۰-۹,]+)", body)
        return m.group(1) if m else None

    return {
        "pending": pick("در انتظار"),
        "processing": pick("در حال پردازش") or pick("درحال پردازش"),
        "completed": pick("تکمیل") or pick("ارسال شده"),
    }


def _is_login_url(url: str) -> bool:
    return "login" in (url or "").lower()


async def _probe_orders(client: httpx.AsyncClient, base: str) -> dict[str, Any] | None:
    orders = await client.get(f"{base}/admin-panel/order/index")
    if _is_login_url(str(orders.url)) or orders.status_code in (401, 403):
        return None
    body = orders.text
    if "LoginForm" in body and "loginform-captcha" in body.lower():
        return None
    title_m = re.search(r"<title>(.*?)</title>", body, flags=re.I | re.S)
    return {
        "ok": True,
        "detail": "admin session ok",
        "url": str(orders.url),
        "title": title_m.group(1).strip() if title_m else "",
        "order_http": orders.status_code,
        "counts": _parse_order_counts(body),
        "via": "cookie_cache",
    }


async def _login_and_orders(
    base: str,
    login_url: str,
    username: str,
    password: str,
    static_captcha: str = "",
    attempts: int = 6,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        cached = _load_cookies()
        if cached:
            client.cookies.update(cached)
            probed = await _probe_orders(client, base)
            if probed:
                return probed

        last: dict[str, Any] = {"ok": False, "detail": "not attempted", "reason_code": "login_failed"}
        for _ in range(attempts):
            page = await client.get(login_url)
            csrf = _extract_csrf(page.text)
            if not csrf:
                last = {
                    "ok": False,
                    "detail": "CSRF از صفحه لاگین خوانده نشد",
                    "reason_code": "csrf_missing",
                }
                continue

            if static_captcha:
                digits = re.sub(r"\D", "", static_captcha)[:3]
            else:
                code = uuid.uuid4().hex
                cap = await client.get(f"{base}/admin-panel/site/captcha", params={"code": code})
                if cap.status_code >= 400 or len(cap.content) < 200:
                    last = {
                        "ok": False,
                        "detail": f"کپچا دریافت نشد status={cap.status_code} size={len(cap.content)}",
                        "reason_code": "captcha_fetch_failed",
                    }
                    continue
                try:
                    digits = _ocr_digits(cap.content)
                except Exception as exc:  # noqa: BLE001
                    return {
                        "ok": False,
                        "detail": f"OCR کپچا در دسترس نیست: {exc}",
                        "reason_code": "ocr_unavailable",
                    }
                if len(digits) < 3:
                    last = {
                        "ok": False,
                        "detail": f"OCR ضعیف: {digits!r}",
                        "reason_code": "ocr_weak",
                    }
                    continue
                digits = digits[:3]

            post = await client.post(
                login_url,
                data={
                    "_csrf-admin": csrf,
                    "LoginForm[username]": username,
                    "LoginForm[password]": password,
                    "LoginForm[captcha]": digits,
                    "LoginForm[rememberMe]": "1",
                    "login-button": "",
                },
            )
            if _is_login_url(str(post.url)):
                last = {
                    "ok": False,
                    "detail": "لاگین رد شد (کپچا/رمز یا هنوز روی صفحه login)",
                    "reason_code": "login_rejected",
                }
                continue

            probed = await _probe_orders(client, base)
            if probed:
                probed["detail"] = "admin login ok"
                probed["via"] = "httpx_ocr"
                _save_cookies(dict(client.cookies))
                return probed

            last = {
                "ok": False,
                "detail": "بعد از لاگین، صفحه سفارش در دسترس نبود",
                "reason_code": "orders_unreachable",
            }

        return last
