from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector
from app.connectors.bots import get_bot_adapter
from app.models import User

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("/status")
async def sources_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    sepidar = SepidarConnector(settings)
    site = MaahedSiteConnector(settings)
    bot = get_bot_adapter(settings)
    return {
        "sepidar": await sepidar.status(),
        "maahed_site": await site.status(),
        "bot": bot.status(),
    }


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
