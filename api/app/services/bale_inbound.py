from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.connectors.bots.bale import BaleBot
from app.connectors.darkube_disk import resolve_upload_dir
from app.models import ManualIngest

logger = logging.getLogger(__name__)

SOURCE_BALE = "bale"
CREATED_BY_PREFIX = "bale"


@dataclass
class InboundFileMeta:
    file_id: str
    filename: str
    kind: str
    mime_type: str | None = None
    file_size: int | None = None


@dataclass
class IngestHandleResult:
    ok: bool
    detail: str
    ingest_id: int | None = None
    filename: str | None = None
    storage: str | None = None
    rejected: bool = False
    skipped: bool = False


def resolve_ingest_allowlist(settings: Settings) -> set[str]:
    """Allowed chat_ids: BALE_INGEST_CHAT_IDS, else BOT_NOTIFY_RECIPIENT."""
    raw = (settings.bale_ingest_chat_ids or "").strip() or (settings.bot_notify_recipient or "").strip()
    ids: set[str] = set()
    for part in re.split(r"[,;\s]+", raw):
        p = part.strip()
        if not p:
            continue
        lower = p.lower()
        if lower.startswith("bale:") or lower.startswith("telegram:") or lower.startswith("tg:"):
            p = p.split(":", 1)[1].strip()
        if p:
            ids.add(p)
    return ids


def chat_id_allowed(chat_id: str | int | None, allowlist: set[str]) -> bool:
    if not allowlist:
        return False
    raw = str(chat_id or "").strip()
    if not raw:
        return False
    return raw in allowlist or raw.lstrip("-") in {a.lstrip("-") for a in allowlist}


def sanitize_filename(name: str | None, *, fallback: str = "file.bin") -> str:
    base = Path((name or "").strip() or fallback).name
    cleaned = re.sub(r"[^\w.\-() \u0600-\u06FF]+", "_", base, flags=re.UNICODE).strip("._ ")
    return (cleaned[:200] if cleaned else fallback)


def extract_inbound_file(message: dict[str, Any]) -> InboundFileMeta | None:
    """Pull document / photo / video / audio / voice file_id from a Bale/Telegram message."""
    if not isinstance(message, dict):
        return None

    doc = message.get("document")
    if isinstance(doc, dict) and doc.get("file_id"):
        return InboundFileMeta(
            file_id=str(doc["file_id"]),
            filename=sanitize_filename(doc.get("file_name"), fallback="document.bin"),
            kind="document",
            mime_type=doc.get("mime_type"),
            file_size=doc.get("file_size"),
        )

    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        largest = max(
            (p for p in photos if isinstance(p, dict) and p.get("file_id")),
            key=lambda p: int(p.get("file_size") or 0),
            default=None,
        )
        if largest:
            return InboundFileMeta(
                file_id=str(largest["file_id"]),
                filename=sanitize_filename(f"photo_{largest['file_id']}.jpg"),
                kind="photo",
                mime_type="image/jpeg",
                file_size=largest.get("file_size"),
            )

    for kind, fallback in (
        ("video", "video.mp4"),
        ("audio", "audio.mp3"),
        ("voice", "voice.ogg"),
        ("video_note", "video_note.mp4"),
    ):
        obj = message.get(kind)
        if isinstance(obj, dict) and obj.get("file_id"):
            name = obj.get("file_name") or fallback
            return InboundFileMeta(
                file_id=str(obj["file_id"]),
                filename=sanitize_filename(name, fallback=fallback),
                kind=kind,
                mime_type=obj.get("mime_type"),
                file_size=obj.get("file_size"),
            )
    return None


def inbound_status_payload(settings: Settings, *, active_mode: str | None = None) -> dict[str, Any]:
    allowlist = resolve_ingest_allowlist(settings)
    token_ok = bool((settings.bale_bot_token or "").strip())
    mode = resolve_ingest_mode(settings)
    available = token_ok and bool(allowlist) and mode != "off"
    return {
        "available": available,
        "label": "دریافت فایل از بله",
        "configured_token": token_ok,
        "allowlist_count": len(allowlist),
        "allowlist_configured": bool(allowlist),
        "mode": active_mode or mode,
        "webhook_path": "/api/bots/bale/webhook",
        "detail": (
            "فعال — فایل از چت‌های مجاز ذخیره می‌شود"
            if available
            else "نیاز به BALE_BOT_TOKEN و لیست chat_id مجاز (BALE_INGEST_CHAT_IDS یا BOT_NOTIFY_RECIPIENT)"
        ),
    }


def resolve_ingest_mode(settings: Settings) -> str:
    raw = (settings.bale_ingest_mode or "auto").strip().lower()
    if raw in {"webhook", "poll", "off"}:
        return raw
    # auto
    base = (settings.app_public_base_url or "").strip().lower()
    if base.startswith("https://") and "localhost" not in base and "127.0.0.1" not in base:
        return "webhook"
    return "poll"


def webhook_public_url(settings: Settings) -> str:
    base = (settings.app_public_base_url or "").rstrip("/")
    return f"{base}/api/bots/bale/webhook"


async def save_inbound_bytes(
    *,
    db: AsyncSession,
    settings: Settings,
    content: bytes,
    original_filename: str,
    chat_id: str,
    kind: str,
    caption: str | None = None,
    message_id: str | int | None = None,
) -> tuple[ManualIngest, Path]:
    upload_dir = resolve_upload_dir(settings)
    safe_name = sanitize_filename(original_filename)
    stored = f"{uuid4().hex}_{safe_name}"
    dest = upload_dir / stored
    dest.write_bytes(content)

    desc_parts = [f"kind={kind}", f"chat_id={chat_id}"]
    if message_id is not None:
        desc_parts.append(f"message_id={message_id}")
    if caption:
        desc_parts.append(f"caption={caption[:500]}")
    row = ManualIngest(
        source=SOURCE_BALE,
        data_date=date.today().isoformat(),
        description="; ".join(desc_parts),
        filename=stored,
        created_by=f"{CREATED_BY_PREFIX}:{chat_id}"[:64],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, upload_dir


async def handle_bale_update(
    update: dict[str, Any],
    *,
    bot: BaleBot,
    db: AsyncSession,
    settings: Settings,
) -> IngestHandleResult:
    message = update.get("message") or update.get("edited_message")
    if not isinstance(message, dict):
        return IngestHandleResult(ok=True, detail="no message", skipped=True)

    chat = message.get("chat") or {}
    chat_id = str((chat.get("id") if isinstance(chat, dict) else "") or "")
    allowlist = resolve_ingest_allowlist(settings)

    meta = extract_inbound_file(message)
    if meta is None:
        # Ignore plain text /start etc. unless we want a help reply — keep quiet for noise.
        return IngestHandleResult(ok=True, detail="no file attachment", skipped=True)

    if not chat_id_allowed(chat_id, allowlist):
        await bot.send_message(
            chat_id,
            "دسترسی ندارید؛ فقط chat_idهای مجاز می‌توانند فایل بفرستند.",
        )
        return IngestHandleResult(
            ok=False,
            detail="chat_id not allowlisted",
            rejected=True,
        )

    try:
        file_info = await bot.get_file(meta.file_id)
        file_path = str(file_info.get("file_path") or "")
        if not file_path:
            raise RuntimeError("getFile returned empty file_path")
        content = await bot.download_file(file_path)
        row, upload_dir = await save_inbound_bytes(
            db=db,
            settings=settings,
            content=content,
            original_filename=meta.filename,
            chat_id=chat_id,
            kind=meta.kind,
            caption=message.get("caption") or message.get("text"),
            message_id=message.get("message_id"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("bale inbound save failed: %s", exc)
        await bot.send_message(chat_id, f"خطا در ذخیره فایل: {exc}")
        return IngestHandleResult(ok=False, detail=str(exc))

    confirm = (
        f"فایل ذخیره شد.\n"
        f"id={row.id}\n"
        f"filename={row.filename}\n"
        f"path={upload_dir / (row.filename or '')}\n"
        f"source=bale"
    )
    await bot.send_message(chat_id, confirm)
    return IngestHandleResult(
        ok=True,
        detail="saved",
        ingest_id=row.id,
        filename=row.filename,
        storage=str(upload_dir),
    )


# --- background poller (webhook fallback) ---

_poll_task: asyncio.Task[None] | None = None
_poll_stop: asyncio.Event | None = None
_runtime_mode: str | None = None


def get_runtime_ingest_mode() -> str | None:
    return _runtime_mode


async def start_bale_inbound(settings: Settings) -> dict[str, Any]:
    """Enable webhook or polling based on BALE_INGEST_MODE. Safe no-op if misconfigured."""
    global _poll_task, _poll_stop, _runtime_mode

    await stop_bale_inbound()
    status = inbound_status_payload(settings)
    if not status["available"]:
        _runtime_mode = "off"
        return {**status, "started": False, "reason": "not_configured"}

    bot = BaleBot(settings.bale_bot_token, api_base=settings.bale_api_base_url)
    mode = resolve_ingest_mode(settings)
    info: dict[str, Any] = {"mode": mode, "started": False}

    if mode == "off":
        _runtime_mode = "off"
        return {**status, **info}

    if mode == "webhook":
        url = webhook_public_url(settings)
        secret = (settings.bale_webhook_secret or "").strip() or None
        try:
            await bot.set_webhook(url, secret_token=secret, drop_pending_updates=False)
            _runtime_mode = "webhook"
            info.update({"started": True, "webhook_url": url, "set_webhook": True})
            return {**status, **info, "mode": "webhook"}
        except Exception as exc:  # noqa: BLE001
            logger.warning("setWebhook failed, falling back to poll: %s", exc)
            info["webhook_error"] = str(exc)
            mode = "poll"

    if mode == "poll":
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning("deleteWebhook before poll: %s", exc)
        _poll_stop = asyncio.Event()
        _poll_task = asyncio.create_task(_poll_loop(settings, _poll_stop), name="bale-inbound-poll")
        _runtime_mode = "poll"
        info.update({"started": True, "mode": "poll"})
        return {**status, **info}

    _runtime_mode = mode
    return {**status, **info}


async def stop_bale_inbound() -> None:
    global _poll_task, _poll_stop, _runtime_mode
    if _poll_stop is not None:
        _poll_stop.set()
    if _poll_task is not None:
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            pass
    _poll_task = None
    _poll_stop = None
    _runtime_mode = None


async def _poll_loop(settings: Settings, stop: asyncio.Event) -> None:
    from app.db import SessionLocal

    bot = BaleBot(settings.bale_bot_token, api_base=settings.bale_api_base_url)
    offset: int | None = None
    logger.info("bale inbound poller started")
    while not stop.is_set():
        try:
            updates = await bot.get_updates(offset=offset, timeout=25)
            for update in updates:
                uid = update.get("update_id")
                if isinstance(uid, int):
                    offset = uid + 1
                async with SessionLocal() as db:
                    await handle_bale_update(update, bot=bot, db=db, settings=settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("bale poll error: %s", exc)
            try:
                await asyncio.wait_for(stop.wait(), timeout=5.0)
            except TimeoutError:
                pass
    logger.info("bale inbound poller stopped")
