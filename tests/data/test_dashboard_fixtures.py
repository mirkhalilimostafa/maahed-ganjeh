"""Data-accuracy fixtures: known inputs → expected widget fields/freshness."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.services.dashboard_engine import propose_widgets  # noqa: E402


class FakeSepidar:
    def __init__(self, ok=True):
        self.ok = ok

    async def status(self):
        if self.ok:
            return {
                "source": "sepidar",
                "ok": True,
                "configured": True,
                "freshness_label": "داده مالی سپیدار: به‌روز لحظه‌ای",
                "detail": "ok",
            }
        return {
            "source": "sepidar",
            "ok": False,
            "configured": False,
            "freshness_label": "سپیدار: توکن تنظیم نشده",
            "detail": "missing",
        }

    async def sample_sales_review(self, from_date, to_date):
        return {
            "ok": True,
            "data": {
                "fixture": True,
                "rows": [{"party": "مشتری الف", "amount": 1_250_000}],
                "from": from_date,
                "to": to_date,
            },
        }


class FakeSite:
    async def status(self):
        return {
            "source": "maahed_site",
            "ok": True,
            "configured": True,
            "freshness_label": "داده فروش تا تاریخ ۱۴۰۴/۰۵/۰۶",
            "detail": "ok",
        }

    async def sample_public_snapshot(self):
        return {"ok": True, "title": "fixture-site", "freshness_label": "داده فروش تا تاریخ ۱۴۰۴/۰۵/۰۶"}


@pytest.mark.asyncio
async def test_investor_request_includes_framing_and_source_fields():
    widgets = await propose_widgets(
        "ساخت داشبورد برای جلسه با سرمایه‌گذار جدید شامل رشد فروش و مالی پایه",
        FakeSepidar(ok=True),
        FakeSite(),
    )
    keys = [w["key"] for w in widgets]
    assert "investor_framing" in keys
    assert "sales_performance" in keys
    assert "finance_baseline" in keys
    assert "site_channel" in keys
    for w in widgets:
        assert w["freshness_label"], f"missing freshness on {w['key']}"
        assert w["source_field"], f"missing source_field on {w['key']}"

    sales = next(w for w in widgets if w["key"] == "sales_performance")
    assert sales["data"]["sepidar_sales_review"]["ok"] is True
    assert sales["data"]["sepidar_sales_review"]["data"]["rows"][0]["amount"] == 1_250_000
    assert "سپیدار.get_sales_review" in sales["source_field"]

    finance = next(w for w in widgets if w["key"] == "finance_baseline")
    assert "بدون تعریف مفهوم" in finance["data"]["disclaimer"] or "سپیدار" in finance["source_field"]


@pytest.mark.asyncio
async def test_offline_sepidar_still_labels_source_honestly():
    widgets = await propose_widgets("گزارش فروش ماهانه", FakeSepidar(ok=False), FakeSite())
    sales = next(w for w in widgets if w["key"] == "sales_performance")
    assert "آفلاین" in sales["source_field"] or "توکن" in sales["freshness_label"] or sales["data"]["sepidar_sales_review"]["ok"] is False
    site = next(w for w in widgets if w["key"] == "site_channel")
    assert "۱۴۰۴/۰۵/۰۶" in site["freshness_label"]
