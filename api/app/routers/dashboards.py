from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.bots import get_bot_adapter
from app.connectors.darkube_disk import DarkubeDiskConnector
from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector
from app.db import get_db
from app.models import BotOutbox, Dashboard, User
from app.services.dashboard_engine import (
    create_dashboard_from_request,
    dashboard_to_dict,
    get_dashboard,
    publish_dashboard,
    revise_dashboard,
)

router = APIRouter(prefix="/api/dashboards", tags=["dashboards"])


def _public_base(request: Request) -> str:
    """Prefer live request host so share links work even if env points at a dead alias."""
    settings = get_settings()
    configured = (settings.app_public_base_url or "").rstrip("/")
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host:
        proto = forwarded_proto or request.url.scheme or "https"
        return f"{proto}://{forwarded_host}".rstrip("/")
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


class CreateDashboardIn(BaseModel):
    request_text: str = Field(min_length=3)
    title: str | None = None
    notify_recipient: str = ""
    # Optional source ids from GET /api/sources (e.g. darkube_disk). Sepidar/site stay default.
    sources: list[str] | None = None


class ReviseIn(BaseModel):
    revision_notes: str = Field(min_length=1)
    notify_recipient: str = ""
    sources: list[str] | None = None


def _resolve_notify_recipient(explicit: str, user: User) -> tuple[str, str | None]:
    """Pick a messenger chat_id. Never use panel username as Bale/Telegram chat_id."""
    settings = get_settings()
    candidates = [
        (explicit or "").strip(),
        (settings.bot_notify_recipient or "").strip(),
    ]
    for raw in candidates:
        if not raw:
            continue
        # Strip optional channel prefix for numeric check
        core = raw.split(":", 1)[-1].strip() if ":" in raw else raw
        if core.lstrip("-").isdigit() or raw.lower().startswith(("bale:", "telegram:", "tg:")):
            return raw, None
        # Non-numeric explicit recipient might still be a stub/username target in stub mode
        if get_bot_adapter(settings).channel == "stub":
            return raw, None
    # Last resort: only username when stub (dev), else skip with clear reason
    bot = get_bot_adapter(settings)
    if bot.channel == "stub":
        return user.username, None
    return "", (
        "گیرنده اعلان تنظیم نشده؛ BOT_NOTIFY_RECIPIENT را روی chat_id بله بگذارید "
        "(مثلاً 1566616156) یا notify_recipient را در درخواست بفرستید"
    )


async def _notify_link(db: AsyncSession, user: User, recipient: str, url: str, title: str) -> dict[str, Any]:
    settings = get_settings()
    bot = get_bot_adapter(settings)
    target, skip_reason = _resolve_notify_recipient(recipient, user)
    if skip_reason:
        return {"ok": False, "channel": bot.channel, "detail": skip_reason}
    message = f"داشبورد آماده شد: {title}\n{url}"
    result = await bot.send_message(target, message, {"dashboard_url": url})
    db.add(
        BotOutbox(
            channel=result.channel,
            recipient=target,
            message=message,
            payload={"dashboard_url": url, "by": user.username},
        )
    )
    await db.commit()
    return {"ok": result.ok, "channel": result.channel, "detail": result.detail}


@router.post("")
async def create_dashboard(
    body: CreateDashboardIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    settings = get_settings()
    dash = await create_dashboard_from_request(
        db,
        request_text=body.request_text,
        created_by=user.username,
        sepidar=SepidarConnector(settings),
        site=MaahedSiteConnector(settings),
        title=body.title,
        disk=DarkubeDiskConnector(settings),
        selected_sources=body.sources,
    )
    payload = dashboard_to_dict(dash, _public_base(request))
    notify = await _notify_link(db, user, body.notify_recipient, payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload


@router.get("")
async def list_dashboards(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(Dashboard).options(selectinload(Dashboard.widgets)).order_by(Dashboard.id.desc()).limit(50)
    )
    rows = result.scalars().unique().all()
    base = _public_base(request)
    return [dashboard_to_dict(d, base) for d in rows]


@router.get("/{public_id}")
async def get_one(
    public_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Public read by link — MVP investor share."""
    dash = await get_dashboard(db, public_id)
    if dash is None:
        raise HTTPException(status_code=404, detail="داشبورد یافت نشد")
    return dashboard_to_dict(dash, _public_base(request))


@router.post("/{public_id}/revise")
async def revise(
    public_id: str,
    body: ReviseIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    settings = get_settings()
    try:
        dash = await revise_dashboard(
            db,
            public_id,
            body.revision_notes,
            SepidarConnector(settings),
            MaahedSiteConnector(settings),
            disk=DarkubeDiskConnector(settings),
            selected_sources=body.sources,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = dashboard_to_dict(dash, _public_base(request))
    notify = await _notify_link(db, user, body.notify_recipient, payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload


@router.post("/{public_id}/publish")
async def publish(
    public_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    try:
        dash = await publish_dashboard(db, public_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = dashboard_to_dict(dash, _public_base(request))
    notify = await _notify_link(db, user, "", payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload
