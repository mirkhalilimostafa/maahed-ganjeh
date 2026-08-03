import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import get_settings
from app.connectors.bots import get_bale_bot, get_bot_adapter, get_stub_bot
from app.db import get_db
from app.models import BotOutbox, User
from app.services.bale_inbound import (
    get_runtime_ingest_mode,
    handle_bale_update,
    inbound_status_payload,
    start_bale_inbound,
    webhook_public_url,
)

router = APIRouter(prefix="/api/bots", tags=["bots"])


class SendMessageIn(BaseModel):
    recipient: str = ""
    message: str = Field(min_length=1)
    payload: dict[str, Any] | None = None


@router.get("/status")
async def bot_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    bot = get_bot_adapter(settings)
    status = bot.status()
    if isinstance(status, dict):
        status = {
            **status,
            "inbound_file_receive": inbound_status_payload(
                settings,
                active_mode=get_runtime_ingest_mode(),
            ),
        }
    return status


@router.get("/env-check")
async def bot_env_check(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Diagnose whether bot tokens reached the process (booleans + key names only)."""
    settings = get_settings()
    keys = sorted(
        k
        for k in os.environ
        if any(
            s in k.upper()
            for s in (
                "BALE",
                "TELEGRAM",
                "BOT_TOKEN",
                "BOT_NOTIFY",
                "SEPIDAR_MCP_TOKEN",
            )
        )
    )
    return {
        "os_bale_set": bool(os.environ.get("BALE_BOT_TOKEN", "").strip()),
        "os_telegram_set": bool(os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()),
        "os_sepidar_set": bool(os.environ.get("SEPIDAR_MCP_TOKEN", "").strip()),
        "os_bot_notify_set": bool(os.environ.get("BOT_NOTIFY_RECIPIENT", "").strip()),
        "os_bale_ingest_chat_ids_set": bool(os.environ.get("BALE_INGEST_CHAT_IDS", "").strip()),
        "settings_bale_set": bool(settings.bale_bot_token.strip()),
        "settings_telegram_set": bool(settings.telegram_bot_token.strip()),
        "inbound_file_receive": inbound_status_payload(
            settings,
            active_mode=get_runtime_ingest_mode(),
        ),
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


@router.post("/bale/webhook")
async def bale_webhook(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    """Public Bale/Telegram webhook — no JWT. Optional secret header when configured."""
    settings = get_settings()
    expected = (settings.bale_webhook_secret or "").strip()
    if expected and (x_telegram_bot_api_secret_token or "").strip() != expected:
        raise HTTPException(status_code=403, detail="invalid webhook secret")

    bot = get_bale_bot(settings)
    if bot is None:
        raise HTTPException(status_code=503, detail="Bale bot not configured")

    try:
        update = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

    if not isinstance(update, dict):
        raise HTTPException(status_code=400, detail="update must be an object")

    result = await handle_bale_update(update, bot=bot, db=db, settings=settings)
    return {
        "ok": result.ok,
        "detail": result.detail,
        "ingest_id": result.ingest_id,
        "filename": result.filename,
        "rejected": result.rejected,
        "skipped": result.skipped,
    }


@router.get("/bale/inbound-status")
async def bale_inbound_status(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    settings = get_settings()
    payload = inbound_status_payload(settings, active_mode=get_runtime_ingest_mode())
    webhook_info: dict[str, Any] | None = None
    bot = get_bale_bot(settings)
    if bot is not None:
        try:
            webhook_info = await bot.get_webhook_info()
        except Exception as exc:  # noqa: BLE001
            webhook_info = {"error": str(exc)}
    return {
        **payload,
        "webhook_url": webhook_public_url(settings),
        "webhook_info": webhook_info,
    }


@router.post("/bale/set-webhook")
async def bale_set_webhook(_user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    """Re-run inbound startup (setWebhook or start poller). Admin only via JWT."""
    settings = get_settings()
    return await start_bale_inbound(settings)
