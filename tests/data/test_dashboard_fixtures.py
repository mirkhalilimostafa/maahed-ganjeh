"""Data-accuracy fixtures: known inputs → expected widget fields/freshness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "api"))

from app.services.dashboard_engine import propose_widgets, summarize_sales_items  # noqa: E402


class FakeSepidar:
    def __init__(self, ok=True, sales_review=None, sales_items=None, banks=None):
        self.ok = ok
        self.sales_review = sales_review
        self.sales_items = sales_items
        self.banks = banks

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
        if self.sales_review is not None:
            return self.sales_review
        return {
            "ok": True,
            "data": {
                "fixture": True,
                "rows": [{"party": "مشتری الف", "amount": 1_250_000}],
                "from": from_date,
                "to": to_date,
            },
        }

    async def sample_sales_items_review(self, from_date, to_date):
        if self.sales_items is not None:
            return self.sales_items
        return {
            "ok": True,
            "data": [
                {
                    "InvoiceId": 1,
                    "CustomerPartyName": "مشتری الف",
                    "ItemTitle": "کالا ۱",
                    "NetPrice": 1_250_000,
                    "Price": 1_250_000,
                    "Discount": 0,
                    "Tax": 0,
                    "Date": f"{from_date[:7]}-15T00:00:00",
                    "CurrencyTitle": "ريال",
                }
            ],
        }

    async def sample_bank_accounts(self):
        if self.banks is not None:
            return self.banks
        return {
            "ok": True,
            "data": [
                {
                    "BankAccountTitle": "حساب تست",
                    "AccountNo": "123",
                    "AccountTypeTitle": "جاري",
                    "Balance": 10_000_000,
                }
            ],
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
    assert "board_framing" not in keys
    assert "sales_performance" in keys
    assert "finance_baseline" in keys
    assert "site_channel" in keys
    for w in widgets:
        assert w["freshness_label"], f"missing freshness on {w['key']}"
        assert w["source_field"], f"missing source_field on {w['key']}"

    sales = next(w for w in widgets if w["key"] == "sales_performance")
    assert sales["data"]["sepidar_sales_review"]["ok"] is True
    assert "kpis" in sales["data"]
    assert "سپیدار.get_sales" in sales["source_field"] or "سپیدار" in sales["source_field"]

    finance = next(w for w in widgets if w["key"] == "finance_baseline")
    assert "بدون تعریف مفهوم" in finance["data"]["disclaimer"] or "سپیدار" in finance["source_field"]
    assert finance["data"]["cash_banks"]["account_count"] >= 1


@pytest.mark.asyncio
async def test_board_ceo_request_uses_board_framing_not_investor():
    widgets = await propose_widgets(
        "داشبورد مالی برای مدیرعامل جهت گزارش به هیئت‌مدیره با رشد فروش و نقدینگی",
        FakeSepidar(ok=True),
        FakeSite(),
    )
    keys = [w["key"] for w in widgets]
    assert "board_framing" in keys
    assert "investor_framing" not in keys
    board = next(w for w in widgets if w["key"] == "board_framing")
    assert "هیئت" in board["title"] or "هیئت" in board["data"].get("audience", "")


@pytest.mark.asyncio
async def test_empty_sales_review_falls_back_to_items():
    sepidar = FakeSepidar(
        ok=True,
        sales_review={"ok": True, "data": []},
        sales_items={
            "ok": True,
            "data": [
                {
                    "InvoiceId": 9,
                    "CustomerPartyName": "ب",
                    "ItemTitle": "کالا",
                    "NetPrice": 5000,
                    "Price": 5000,
                    "Discount": 0,
                    "Tax": 0,
                    "Date": "2024-06-01T00:00:00",
                }
            ],
        },
    )
    widgets = await propose_widgets("گزارش فروش ماهانه", sepidar, FakeSite())
    sales = next(w for w in widgets if w["key"] == "sales_performance")
    assert "fallback" in sales["source_field"] or "items" in sales["source_field"]
    assert sales["data"]["kpis"]["net_sales"] == 5000
    assert sales["data"]["kpis"]["invoice_count"] == 1


@pytest.mark.asyncio
async def test_offline_sepidar_still_labels_source_honestly():
    widgets = await propose_widgets("گزارش فروش ماهانه", FakeSepidar(ok=False), FakeSite())
    sales = next(w for w in widgets if w["key"] == "sales_performance")
    assert "آفلاین" in sales["source_field"] or "توکن" in sales["freshness_label"] or sales["data"]["sepidar_sales_review"]["ok"] is False
    site = next(w for w in widgets if w["key"] == "site_channel")
    assert "۱۴۰۴/۰۵/۰۶" in site["freshness_label"]


def test_summarize_sales_items_kpis():
    rows = [
        {
            "InvoiceId": 1,
            "CustomerPartyName": "الف",
            "ItemTitle": "کالا",
            "NetPrice": 100,
            "Price": 120,
            "Discount": -20,
            "Tax": 0,
            "Date": "2024-01-10T00:00:00",
        },
        {
            "InvoiceId": 1,
            "CustomerPartyName": "الف",
            "ItemTitle": "کالا۲",
            "NetPrice": 50,
            "Price": 50,
            "Discount": 0,
            "Tax": 5,
            "Date": "2024-01-10T00:00:00",
        },
    ]
    s = summarize_sales_items(rows)
    assert s["invoice_count"] == 1
    assert s["net_sales"] == 150
    assert s["top_customers"][0]["name"] == "الف"
