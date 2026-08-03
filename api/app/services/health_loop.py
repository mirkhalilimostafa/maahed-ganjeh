from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, get_settings
from app.connectors.bots import get_bot_adapter
from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector

logger = logging.getLogger(__name__)

_LAST_ALERT_KEY: dict[str, str] = {}


async def collect_sources_health(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    sepidar = SepidarConnector(settings)
    site = MaahedSiteConnector(settings)
    bot = get_bot_adapter(settings)

    sepidar_status = await sepidar.status()
    site_status = await site.status()
    bot_status = bot.status()
    probe = getattr(bot, "probe", None)
    if callable(probe):
        try:
            me = await probe()
            if isinstance(bot_status, dict):
                bot_status = {**bot_status, "probe": me}
        except Exception as exc:  # noqa: BLE001
            bot_status = {**bot_status, "ok": False, "probe_error": str(exc)}

    data_ok = bool(sepidar_status.get("ok")) or bool(site_status.get("ok"))
    checks = {
        "sepidar": sepidar_status,
        "maahed_site": site_status,
        "bot": bot_status,
        "data": {
            "ok": data_ok,
            "detail": "حداقل یکی از سپیدار یا سایت سفارش داده می‌دهد"
            if data_ok
            else "هیچ منبع داده‌ای (سپیدار/سایت) در دسترس نیست",
            "reason_code": None if data_ok else "no_data_source",
        },
    }
    failures = [
        {"name": name, **_failure_payload(payload)}
        for name, payload in checks.items()
        if not payload.get("ok")
    ]
    return {
        "ok": not failures,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "failures": failures,
    }


def _failure_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "detail": payload.get("detail") or payload.get("freshness_label") or "قطع",
        "reason_code": payload.get("reason_code") or payload.get("probe_error") or "down",
        "freshness_label": payload.get("freshness_label"),
    }


def _format_bale_message(report: dict[str, Any]) -> str:
    lines = ["⚠️ گنجه — قطعی منابع", f"زمان: {report.get('checked_at')}"]
    labels = {
        "sepidar": "سپیدار",
        "maahed_site": "سایت ماهد",
        "bot": "بات",
        "data": "داده فروش/مالی",
    }
    for item in report.get("failures") or []:
        name = labels.get(item.get("name"), item.get("name"))
        reason = item.get("reason_code") or "unknown"
        detail = item.get("detail") or "—"
        lines.append(f"• {name}: قطع است")
        lines.append(f"  دلیل: {detail}")
        lines.append(f"  کد: {reason}")
        lines.append(f"  → فعلاً نمی‌توان وصل شد / داده گرفت")
    return "\n".join(lines)


async def run_login_health_loop(settings: Settings | None = None) -> dict[str, Any]:
    """On each panel login: probe sources; if down and unrecoverable, notify Bale once per fingerprint."""
    settings = settings or get_settings()
    report = await collect_sources_health(settings)
    notify: dict[str, Any] = {"skipped": True, "reason": "all_ok"}

    if report.get("ok"):
        _LAST_ALERT_KEY.clear()
        return {**report, "notify": notify}

    fingerprint = "|".join(
        f"{f.get('name')}:{f.get('reason_code')}" for f in (report.get("failures") or [])
    )
    recipient = (settings.bot_notify_recipient or "").strip()
    if not recipient:
        notify = {
            "skipped": True,
            "reason": "BOT_NOTIFY_RECIPIENT تنظیم نشده",
            "fingerprint": fingerprint,
        }
        return {**report, "notify": notify}

    if _LAST_ALERT_KEY.get("fp") == fingerprint:
        notify = {"skipped": True, "reason": "duplicate_alert", "fingerprint": fingerprint}
        return {**report, "notify": notify}

    bot = get_bot_adapter(settings)
    if bot.channel == "stub":
        notify = {
            "skipped": True,
            "reason": "بات Stub است (توکن بله/تلگرام نیست)",
            "fingerprint": fingerprint,
        }
        return {**report, "notify": notify}

    message = _format_bale_message(report)
    try:
        result = await bot.send_message(recipient, message)
        notify = {
            "skipped": False,
            "ok": result.ok,
            "channel": result.channel,
            "detail": result.detail,
            "fingerprint": fingerprint,
        }
        if result.ok:
            _LAST_ALERT_KEY["fp"] = fingerprint
    except Exception as exc:  # noqa: BLE001
        logger.exception("health notify failed")
        notify = {"skipped": False, "ok": False, "detail": str(exc), "fingerprint": fingerprint}

    return {**report, "notify": notify}
