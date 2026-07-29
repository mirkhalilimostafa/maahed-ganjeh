from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.bots import get_bot_adapter
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


class CreateDashboardIn(BaseModel):
    request_text: str = Field(min_length=3)
    title: str | None = None
    notify_recipient: str = ""


class ReviseIn(BaseModel):
    revision_notes: str = Field(min_length=1)
    notify_recipient: str = ""


async def _notify_link(db: AsyncSession, user: User, recipient: str, url: str, title: str) -> dict[str, Any]:
    settings = get_settings()
    bot = get_bot_adapter(settings)
    message = f"داشبورد آماده شد: {title}\n{url}"
    result = await bot.send_message(recipient or user.username, message, {"dashboard_url": url})
    db.add(
        BotOutbox(
            channel=result.channel,
            recipient=recipient or user.username,
            message=message,
            payload={"dashboard_url": url, "by": user.username},
        )
    )
    await db.commit()
    return {"ok": result.ok, "channel": result.channel, "detail": result.detail}


@router.post("")
async def create_dashboard(
    body: CreateDashboardIn,
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
    )
    payload = dashboard_to_dict(dash, settings.app_public_base_url)
    notify = await _notify_link(db, user, body.notify_recipient, payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload


@router.get("")
async def list_dashboards(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, Any]]:
    settings = get_settings()
    result = await db.execute(
        select(Dashboard).options(selectinload(Dashboard.widgets)).order_by(Dashboard.id.desc()).limit(50)
    )
    rows = result.scalars().unique().all()
    return [dashboard_to_dict(d, settings.app_public_base_url) for d in rows]


@router.get("/{public_id}")
async def get_one(
    public_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """Public read by link — MVP investor share."""
    settings = get_settings()
    dash = await get_dashboard(db, public_id)
    if dash is None:
        raise HTTPException(status_code=404, detail="داشبورد یافت نشد")
    return dashboard_to_dict(dash, settings.app_public_base_url)


@router.post("/{public_id}/revise")
async def revise(
    public_id: str,
    body: ReviseIn,
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
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = dashboard_to_dict(dash, settings.app_public_base_url)
    notify = await _notify_link(db, user, body.notify_recipient, payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload


@router.post("/{public_id}/publish")
async def publish(
    public_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    settings = get_settings()
    try:
        dash = await publish_dashboard(db, public_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = dashboard_to_dict(dash, settings.app_public_base_url)
    notify = await _notify_link(db, user, "", payload["url"], payload["title"])
    payload["bot_notify"] = notify
    return payload
