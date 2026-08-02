"""Local smoke: unwrap + board dashboard propose against live Sepidar from .env."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api"))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from app.config import get_settings  # noqa: E402
from app.connectors.sepidar import SepidarConnector, _unwrap_tool_payload  # noqa: E402
from app.connectors.site import MaahedSiteConnector  # noqa: E402
from app.services.dashboard_engine import propose_widgets  # noqa: E402


def test_unwrap() -> None:
    raw = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        [
                            {
                                "NetPrice": 100,
                                "InvoiceId": 1,
                                "CustomerPartyName": "A",
                                "ItemTitle": "X",
                                "Date": "2024-01-01",
                                "Price": 100,
                                "Discount": 0,
                                "Tax": 0,
                            }
                        ]
                    ),
                }
            ]
        },
    }
    out = _unwrap_tool_payload(raw)
    assert isinstance(out, list) and out[0]["NetPrice"] == 100
    print("unwrap_ok")


async def main() -> None:
    test_unwrap()
    get_settings.cache_clear()
    settings = get_settings()
    sepidar = SepidarConnector(settings)
    site = MaahedSiteConnector(settings)
    widgets = await propose_widgets(
        "داشبورد مالی برای مدیرعامل جهت گزارش به هیئت‌مدیره: درآمد و رشد فروش، نقدینگی و کانال سایت",
        sepidar,
        site,
    )
    keys = [w["key"] for w in widgets]
    print("keys", keys)
    assert "board_framing" in keys
    assert "investor_framing" not in keys
    sales = next(w for w in widgets if w["key"] == "sales_performance")
    fin = next(w for w in widgets if w["key"] == "finance_baseline")
    print("sales_source", sales["source_field"].encode("ascii", "backslashreplace").decode())
    print("kpis", json.dumps(sales["data"].get("kpis"), ensure_ascii=True)[:500])
    print("finance_source", fin["source_field"].encode("ascii", "backslashreplace").decode())
    cash = (fin["data"] or {}).get("cash_banks") or {}
    print("banks", cash.get("account_count"), "sum", cash.get("balance_sum_raw"))
    print("period", sales["data"].get("period"))
    kpis = sales["data"].get("kpis") or {}
    print("net_sales", kpis.get("net_sales"), "invoices", kpis.get("invoice_count"), "rows", kpis.get("row_count"))
    assert "kpis" in sales["data"]
    # Persist a short report for inspection
    out = {
        "keys": keys,
        "sales_source": sales["source_field"],
        "kpis": kpis,
        "period": sales["data"].get("period"),
        "finance_source": fin["source_field"],
        "cash_banks_summary": {
            "account_count": cash.get("account_count"),
            "balance_sum_raw": cash.get("balance_sum_raw"),
        },
    }
    (ROOT / "tmp_board_smoke.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUCCESS")


if __name__ == "__main__":
    asyncio.run(main())
