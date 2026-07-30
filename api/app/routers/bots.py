import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.bots import get_bot_adapter, get_stub_bot
from app.db import get_db
from app.models import BotOutbox, User

router = APIRouter(prefix="/api/bots", tags=["bots"])


class SendMessageIn(BaseModel):
    recipient: str = ""
    message: str = Field(min_length=1)
    payload: dict[str, Any] | None = None


@router.get("/status")
async def bot_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    bot = get_bot_adapter(settings)
    return bot.status()


@router.get("/env-check")
async def bot_env_check(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Diagnose whether bot tokens reached the process (booleans + key names only)."""
    settings = get_settings()
    keys = sorted(
        k
        for k in os.environ
        if any(s in k.upper() for s in ("BALE", "TELEGRAM", "BOT_TOKEN", "SEPIDAR_MCP_TOKEN"))
    )
    return {
        "os_bale_set": bool(os.environ.get("BALE_BOT_TOKEN", "").strip()),
        "os_telegram_set": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        "os_sepidar_set": bool(os.environ.get("SEPIDAR_MCP_TOKEN", "").strip()),
        "settings_bale_set": bool(settings.bale_bot_token.strip()),
        "settings_telegram_set": bool(settings.telegram_bot_token.strip()),
        "matching_env_keys": keys,
    }


@router.post("/send")
async def bot_send(
    body: SendMessageIn,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    settings = get_settings()
    bot = get_bot_adapter(settings)
    result = await bot.send_message(body.recipient, body.message, body.payload)
    db.add(
        BotOutbox(
            channel=result.channel,
            recipient=body.recipient,
            message=body.message,
            payload={"by": user.username, **(body.payload or {})},
        )
    )
    await db.commit()
    return {
        "ok": result.ok,
        "channel": result.channel,
        "detail": result.detail,
        "message_id": result.message_id,
    }


@router.get("/stub/recent")
async def stub_recent(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    return {"items": get_stub_bot().recent}
