from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.darkube_disk import DarkubeDiskConnector, SOURCE_ID as DISK_ID, SOURCE_LABEL as DISK_LABEL
from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector
from app.connectors.bots import get_bot_adapter
from app.models import User
from app.services.health_loop import run_login_health_loop

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def sources_catalog(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Taxonomy of first-class sources (ERP / site / storage) plus notify channel."""
    return {
        "sources": [
            {
                "id": "sepidar",
                "label": "سپیدار",
                "kind": "erp_live",
                "role": "اعداد زنده مالی و فروش از MCP سپیدار",
                "selectable_for_dashboard": True,
            },
            {
                "id": "maahed_site",
                "label": "سایت ماهد",
                "kind": "website",
                "role": "سفارش و کانال فروش maahed.ir",
                "selectable_for_dashboard": True,
            },
            {
                "id": DISK_ID,
                "label": DISK_LABEL,
                "kind": "persistent_storage",
                "role": "فایل‌های آپلود و SQLite روی PVC دارکوب (/data) — نه ERP زنده",
                "selectable_for_dashboard": True,
            },
            {
                "id": "bot",
                "label": "بات (اعلان)",
                "kind": "notify_channel",
                "role": "کانال اعلان بله/تلگرام — منبع داده نیست",
                "selectable_for_dashboard": False,
            },
        ]
    }


@router.get("/status")
async def sources_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    sepidar = SepidarConnector(settings)
    site = MaahedSiteConnector(settings)
    disk = DarkubeDiskConnector(settings)
    bot = get_bot_adapter(settings)
    bot_status = bot.status()
    if isinstance(bot_status, dict):
        bot_status = {
            **bot_status,
            "label": bot_status.get("label") or "بات (اعلان)",
            "kind": "notify_channel",
        }
    probe = getattr(bot, "probe", None)
    if callable(probe):
        try:
            me = await probe()
            if isinstance(bot_status, dict):
                bot_status = {**bot_status, "probe": me}
        except Exception as exc:  # noqa: BLE001
            bot_status = {**bot_status, "probe_error": str(exc)}
    return {
        "sepidar": await sepidar.status(),
        "maahed_site": await site.status(),
        "darkube_disk": await disk.status(),
        "bot": bot_status,
    }


@router.post("/health-loop")
async def sources_health_loop(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """اجرای دستی لوپ سلامت + اعلان بله در صورت قطعی."""
    return await run_login_health_loop(get_settings())


@router.get("/sepidar/sample")
async def sepidar_sample(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    sepidar = SepidarConnector(settings)
    status = await sepidar.status()
    if not status.get("ok"):
        return {"ok": False, "status": status}
    from datetime import date, timedelta

    to_date = date.today().isoformat()
    from_date = (date.today() - timedelta(days=30)).isoformat()
    sample = await sepidar.sample_sales_review(from_date, to_date)
    return {
        "ok": True,
        "freshness_label": status.get("freshness_label"),
        "source_field": "سپیدار.get_sales_review",
        "sample": sample,
    }


@router.get("/site/sample")
async def site_sample(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    site = MaahedSiteConnector(settings)
    status = await site.status()
    snap = await site.sample_public_snapshot()
    return {"ok": True, "status": status, "snapshot": snap}


@router.get("/darkube-disk/sample")
async def darkube_disk_sample(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    disk = DarkubeDiskConnector(settings)
    status = await disk.status()
    return {
        "ok": bool(status.get("ok")),
        "status": status,
        "source_field": "دیسک پایدار.وضعیت_مونت_و_آپلود",
        "hint": "فایل‌ها از /ingest (manual-ingest) روی UPLOAD_DIR ذخیره می‌شوند",
    }
