"""Unit tests for Bale inbound file receive → ManualIngest."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# Force sqlite before app.db creates its engine (avoids asyncpg on DATABASE_URL from .env).
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.config import Settings, get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import Base  # noqa: E402
from app.services.bale_inbound import (  # noqa: E402
    chat_id_allowed,
    extract_inbound_file,
    handle_bale_update,
    inbound_status_payload,
    resolve_ingest_allowlist,
    resolve_ingest_mode,
    sanitize_filename,
    save_inbound_bytes,
)


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    return Settings(
        bale_bot_token="test-token",
        bot_notify_recipient="1566616156",
        bale_ingest_chat_ids="",
        bale_ingest_mode="webhook",
        app_public_base_url="https://maahed-ganjeh-tehran.darkube.ir",
        upload_dir=str(upload),
        database_url=f"sqlite+aiosqlite:///{tmp_path / 't.db'}",
    )


@pytest_asyncio.fixture
async def db_session(tmp_path) -> AsyncSession:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ingest.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


def test_sanitize_filename_strips_path_and_keeps_persian():
    assert sanitize_filename("../../x/گزارش.xlsx") == "گزارش.xlsx"
    assert sanitize_filename("") == "file.bin"


def test_extract_document_and_photo():
    doc = extract_inbound_file(
        {"document": {"file_id": "f1", "file_name": "a.csv", "mime_type": "text/csv", "file_size": 10}}
    )
    assert doc is not None
    assert doc.file_id == "f1"
    assert doc.filename == "a.csv"
    assert doc.kind == "document"

    photo = extract_inbound_file(
        {
            "photo": [
                {"file_id": "small", "file_size": 1},
                {"file_id": "big", "file_size": 99},
            ]
        }
    )
    assert photo is not None
    assert photo.file_id == "big"
    assert photo.kind == "photo"
    assert extract_inbound_file({"text": "hi"}) is None


def test_allowlist_from_notify_and_ingest_ids(settings):
    assert resolve_ingest_allowlist(settings) == {"1566616156"}
    assert chat_id_allowed(1566616156, resolve_ingest_allowlist(settings))
    assert not chat_id_allowed("999", resolve_ingest_allowlist(settings))

    settings.bale_ingest_chat_ids = "bale:111, 222"
    assert resolve_ingest_allowlist(settings) == {"111", "222"}


def test_resolve_ingest_mode_auto(settings):
    settings.bale_ingest_mode = "auto"
    assert resolve_ingest_mode(settings) == "webhook"
    settings.app_public_base_url = "http://localhost:8080"
    assert resolve_ingest_mode(settings) == "poll"


def test_inbound_status_available(settings):
    payload = inbound_status_payload(settings)
    assert payload["available"] is True
    assert payload["label"] == "دریافت فایل از بله"
    settings.bale_bot_token = ""
    assert inbound_status_payload(settings)["available"] is False


@pytest.mark.asyncio
async def test_save_inbound_bytes(settings, db_session, tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    upload.mkdir(exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    row, storage = await save_inbound_bytes(
        db=db_session,
        settings=settings,
        content=b"hello-csv",
        original_filename="sample.csv",
        chat_id="1566616156",
        kind="document",
        caption="cap",
        message_id=7,
    )
    assert row.id is not None
    assert row.source == "bale"
    assert row.filename and row.filename.endswith("_sample.csv")
    assert (storage / row.filename).read_bytes() == b"hello-csv"
    assert "chat_id=1566616156" in row.description


class _FakeBale:
    channel = "bale"

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def get_file(self, file_id: str) -> dict[str, Any]:
        assert file_id == "fid-1"
        return {"file_id": file_id, "file_path": "docs/a.csv"}

    async def download_file(self, file_path: str) -> bytes:
        assert file_path == "docs/a.csv"
        return b"file-bytes"

    async def send_message(self, recipient: str, message: str, payload=None):
        self.sent.append((recipient, message))
        return None


@pytest.mark.asyncio
async def test_handle_update_saves_and_replies(settings, db_session, tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    upload.mkdir(exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    bot = _FakeBale()
    update = {
        "update_id": 1,
        "message": {
            "message_id": 42,
            "chat": {"id": 1566616156},
            "document": {"file_id": "fid-1", "file_name": "report.xlsx"},
            "caption": "گزارش ماه",
        },
    }
    result = await handle_bale_update(update, bot=bot, db=db_session, settings=settings)  # type: ignore[arg-type]
    assert result.ok is True
    assert result.ingest_id is not None
    assert result.filename and result.filename.endswith("_report.xlsx")
    assert bot.sent and "فایل ذخیره شد" in bot.sent[0][1]
    assert (upload / result.filename).read_bytes() == b"file-bytes"


@pytest.mark.asyncio
async def test_handle_update_rejects_non_allowlisted(settings, db_session):
    bot = _FakeBale()
    update = {
        "update_id": 2,
        "message": {
            "message_id": 1,
            "chat": {"id": 999999},
            "document": {"file_id": "fid-1", "file_name": "x.bin"},
        },
    }
    result = await handle_bale_update(update, bot=bot, db=db_session, settings=settings)  # type: ignore[arg-type]
    assert result.rejected is True
    assert result.ok is False
    assert bot.sent and "دسترسی ندارید" in bot.sent[0][1]
