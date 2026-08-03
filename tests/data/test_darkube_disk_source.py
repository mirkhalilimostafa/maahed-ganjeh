"""Unit tests for Darkube persistent disk source connector."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.config import Settings  # noqa: E402
from app.connectors.darkube_disk import DarkubeDiskConnector, SOURCE_ID  # noqa: E402
from app.services.dashboard_engine import propose_widgets  # noqa: E402


class FakeSepidar:
    async def status(self):
        return {
            "source": "sepidar",
            "ok": False,
            "configured": False,
            "freshness_label": "سپیدار: توکن تنظیم نشده",
            "detail": "missing",
        }

    async def sample_sales_review(self, from_date, to_date):
        return {"ok": False}

    async def sample_sales_items_review(self, from_date, to_date):
        return {"ok": False, "data": []}

    async def sample_bank_accounts(self):
        return {"ok": False, "data": []}


class FakeSite:
    async def status(self):
        return {
            "source": "maahed_site",
            "ok": True,
            "configured": True,
            "freshness_label": "سایت ok",
            "detail": "ok",
        }

    async def sample_public_snapshot(self):
        return {"ok": True, "title": "fixture"}


@pytest.mark.asyncio
async def test_darkube_disk_status_writable_upload_dir(tmp_path, monkeypatch):
    upload = tmp_path / "uploads"
    upload.mkdir()
    monkeypatch.setenv("UPLOAD_DIR", str(upload))
    settings = Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 't.db'}", upload_dir=str(upload))
    status = await DarkubeDiskConnector(settings).status()
    assert status["source"] == SOURCE_ID
    assert status["label"] == "دیسک پایدار دارکوب"
    assert status["kind"] == "persistent_storage"
    assert status["ok"] is True
    assert status["upload_dir"] == str(upload)
    assert status["related"]["manual_ingest"] == "/ingest"
    assert "usage" in status


@pytest.mark.asyncio
async def test_disk_widget_when_selected_sources():
    class FakeDisk:
        async def status(self):
            return {
                "source": SOURCE_ID,
                "ok": True,
                "freshness_label": "دیسک پایدار دارکوب: متصل و قابل نوشتن",
                "mount_path": "/data",
                "upload_dir": "/data/uploads",
                "usage_label": "1.0 GiB از 10.0 GiB (10.0٪)",
                "upload_file_count": 2,
            }

    widgets = await propose_widgets(
        "گزارش فروش ماهانه",
        FakeSepidar(),
        FakeSite(),
        disk=FakeDisk(),
        selected_sources=["sepidar", "maahed_site", "darkube_disk"],
    )
    keys = [w["key"] for w in widgets]
    assert "darkube_disk_storage" in keys
    disk_w = next(w for w in widgets if w["key"] == "darkube_disk_storage")
    assert disk_w["source"] == SOURCE_ID
    assert "جایگزین" in disk_w["data"]["disclaimer"] or "ERP" in disk_w["data"]["disclaimer"]


@pytest.mark.asyncio
async def test_disk_widget_from_keywords_without_explicit_sources():
    class FakeDisk:
        async def status(self):
            return {
                "source": SOURCE_ID,
                "ok": True,
                "freshness_label": "ok",
                "upload_dir": "/data/uploads",
            }

    widgets = await propose_widgets(
        "وضعیت دیسک پایدار دارکوب و فایل‌های آپلود",
        FakeSepidar(),
        FakeSite(),
        disk=FakeDisk(),
    )
    assert any(w["key"] == "darkube_disk_storage" for w in widgets)


@pytest.mark.asyncio
async def test_plain_sales_request_skips_disk_widget():
    widgets = await propose_widgets("گزارش فروش ماهانه", FakeSepidar(), FakeSite())
    assert all(w["key"] != "darkube_disk_storage" for w in widgets)
