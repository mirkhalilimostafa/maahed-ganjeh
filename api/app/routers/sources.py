from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector
from app.models import User
from app.services.health_loop import collect_sources_health, run_login_health_loop

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/status")
async def sources_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    report = await collect_sources_health(get_settings())
    checks = report.get("checks") or {}
    return {
        "sepidar": checks.get("sepidar"),
        "maahed_site": checks.get("maahed_site"),
        "bot": checks.get("bot"),
        "data": checks.get("data"),
        "ok": report.get("ok"),
        "failures": report.get("failures") or [],
        "checked_at": report.get("checked_at"),
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
