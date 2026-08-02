from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.connectors.sepidar import SepidarConnector
from app.connectors.site import MaahedSiteConnector
from app.models import Dashboard, Widget


# Narrow investor cues — avoid matching generic «رشد/عملکرد» alone (false positives for board/CEO).
INVESTOR_KEYWORDS = (
    "سرمایه\u200cگذار",
    "سرمایه گذار",
    "سرمایهگذار",
    "investor",
    "vc",
)
BOARD_KEYWORDS = (
    "هیئت\u200cمدیره",
    "هیئت مدیره",
    "هیات مدیره",
    "مدیرعامل",
    "ceo",
    "board",
    "گزارش مالی",
    "نقدینگی",
    "مطالبات",
)


def _jalali_approx_label(d: date) -> str:
    # Lightweight Gregorian label; UI can show as-is. Full Jalali conversion can come later.
    return d.isoformat()


def _looks_empty(payload: Any) -> bool:
    if payload is None:
        return True
    if payload == [] or payload == {}:
        return True
    if isinstance(payload, dict):
        if payload.get("ok") is False:
            return True
        data = payload.get("data", payload)
        if data in ([], {}, None, ""):
            return True
        if isinstance(data, dict) and not data:
            return True
    return False


def _as_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, list):
            return [r for r in data if isinstance(r, dict)]
        for key in ("rows", "items", "Items", "result"):
            val = data.get(key) if isinstance(data, dict) else None
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
    return []


def _num(row: dict[str, Any], *keys: str) -> float:
    for k in keys:
        if k in row and row[k] is not None:
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return 0.0


def summarize_sales_items(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Board-friendly KPIs from get_sales_items_review rows (raw Sepidar fields)."""
    if not rows:
        return {
            "row_count": 0,
            "invoice_count": 0,
            "net_sales": 0,
            "gross_sales": 0,
            "discount_total": 0,
            "tax_total": 0,
            "currency": "ریال",
            "top_customers": [],
            "top_items": [],
            "by_month": [],
        }

    invoice_ids: set[Any] = set()
    net = gross = discount = tax = 0.0
    by_customer: dict[str, float] = {}
    by_item: dict[str, float] = {}
    by_month: dict[str, float] = {}
    currency = "ریال"

    for r in rows:
        invoice_ids.add(r.get("InvoiceId") or r.get("EntityId") or r.get("Number"))
        n = _num(r, "NetPriceInBaseCurrency", "NetPrice", "PriceInBaseCurrency", "Price")
        g = _num(r, "PriceInBaseCurrency", "Price")
        d = abs(_num(r, "DiscountInBaseCurrency", "Discount"))
        t = _num(r, "TaxInBaseCurrency", "Tax")
        net += n
        gross += g
        discount += d
        tax += t
        if r.get("CurrencyTitle"):
            currency = str(r["CurrencyTitle"])
        cust = str(r.get("CustomerPartyName") or r.get("CustomerRealName") or "نامشخص").strip()
        item = str(r.get("ItemTitle") or r.get("ItemCode") or "قلم").strip()
        by_customer[cust] = by_customer.get(cust, 0.0) + n
        by_item[item] = by_item.get(item, 0.0) + n
        raw_date = str(r.get("Date") or "")[:7]
        if raw_date:
            by_month[raw_date] = by_month.get(raw_date, 0.0) + n

    def _top(mapping: dict[str, float], n: int = 5) -> list[dict[str, Any]]:
        return [
            {"name": k, "net": round(v)}
            for k, v in sorted(mapping.items(), key=lambda kv: kv[1], reverse=True)[:n]
        ]

    return {
        "row_count": len(rows),
        "invoice_count": len({i for i in invoice_ids if i is not None}),
        "net_sales": round(net),
        "gross_sales": round(gross),
        "discount_total": round(discount),
        "tax_total": round(tax),
        "currency": currency,
        "top_customers": _top(by_customer),
        "top_items": _top(by_item),
        "by_month": [
            {"month": m, "net": round(v)} for m, v in sorted(by_month.items())
        ],
    }


def summarize_bank_accounts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0.0
    accounts: list[dict[str, Any]] = []
    for r in rows[:12]:
        bal = _num(r, "Balance")
        total += bal
        accounts.append(
            {
                "title": r.get("BankAccountTitle") or r.get("AccountNo") or "حساب",
                "account_no": r.get("AccountNo"),
                "type": r.get("AccountTypeTitle"),
                "balance": round(bal),
            }
        )
    return {
        "account_count": len(rows),
        "balance_sum_raw": round(total),
        "accounts": accounts,
        "note": "جمع خام مانده حساب‌های بانکی سپیدار — بدون تعریف مفهوم «نقد عملیاتی»",
    }


async def _fetch_sales_with_fallback(
    sepidar: SepidarConnector,
    from_date: str,
    to_date: str,
) -> tuple[dict[str, Any], str, list[dict[str, Any]], dict[str, Any]]:
    """Prefer sales_review; if empty, fall back to sales_items_review (+ KPI summary)."""
    review = await sepidar.sample_sales_review(from_date, to_date)
    source_field = "سپیدار.get_sales_review"
    rows = _as_rows(review)
    items_payload: dict[str, Any] | None = None

    if _looks_empty(review) or not rows:
        items_payload = await sepidar.sample_sales_items_review(from_date, to_date)
        rows = _as_rows(items_payload)
        if rows:
            source_field = "سپیدار.get_sales_items_review (fallback)"
        else:
            # Widen window once — live clock may be ahead of ledger activity.
            wider_from = (date.fromisoformat(to_date) - timedelta(days=730)).isoformat()
            items_payload = await sepidar.sample_sales_items_review(wider_from, to_date)
            rows = _as_rows(items_payload)
            if rows:
                source_field = "سپیدار.get_sales_items_review (نگاه ۲ساله)"
                from_date = wider_from
            else:
                source_field = "سپیدار.get_sales_review + get_sales_items_review (خالی)"

    summary = summarize_sales_items(rows)
    period = {"from": from_date, "to": to_date}
    payload: dict[str, Any] = {
        "period": period,
        "note": "منبع خام فروش — بدون یکسان‌سازی مفهومی",
        "kpis": summary,
        "sample_rows": rows[:8],
        "sepidar_sales_review": review,
    }
    if items_payload is not None:
        payload["sepidar_sales_items_review"] = {
            "ok": items_payload.get("ok", True) if isinstance(items_payload, dict) else True,
            "row_count": len(rows),
        }
    return payload, source_field, rows, summary


async def propose_widgets(
    request_text: str,
    sepidar: SepidarConnector,
    site: MaahedSiteConnector,
) -> list[dict[str, Any]]:
    """Rule-based propose for v0 (NL → component list). LLM can replace later without API change."""
    text = request_text.strip()
    lower = text.lower()
    is_investor = any(k in text or k in lower for k in INVESTOR_KEYWORDS)
    is_board = any(k in text or k in lower for k in BOARD_KEYWORDS)

    sepidar_status = await sepidar.status()
    site_status = await site.status()

    today = date.today()
    from_date = (today - timedelta(days=90)).isoformat()
    to_date = today.isoformat()
    sales_as_of = site_status.get("freshness_label") or f"داده فروش تا تاریخ {_jalali_approx_label(today - timedelta(days=5))}"

    widgets: list[dict[str, Any]] = []

    # Sales growth / performance
    sales_payload: dict[str, Any]
    sales_source_field: str
    sales_freshness: str
    if sepidar_status.get("configured") and sepidar_status.get("ok"):
        sales_payload, sales_source_field, _rows, _summary = await _fetch_sales_with_fallback(
            sepidar, from_date, to_date
        )
        sales_freshness = sepidar_status.get("freshness_label", "داده مالی سپیدار: به‌روز لحظه‌ای")
    else:
        sales_payload = {
            "period": {"from": from_date, "to": to_date},
            "note": "منبع خام فروش — بدون یکسان‌سازی مفهومی",
            "kpis": summarize_sales_items([]),
            "sample_rows": [],
            "sepidar_sales_review": {"ok": False, "detail": sepidar_status.get("detail")},
        }
        sales_source_field = "سپیدار.get_sales_review (آفلاین/بدون توکن)"
        sales_freshness = sepidar_status.get("freshness_label", "سپیدار: در دسترس نیست")

    widgets.append(
        {
            "key": "sales_performance",
            "title": "عملکرد و رشد فروش",
            "source": "sepidar+site",
            "source_field": sales_source_field,
            "freshness_label": sales_freshness,
            "freshness_kind": "live_or_as_of",
            "sort_order": 1,
            "data": sales_payload,
        }
    )

    # Site channel signal
    site_snap: dict[str, Any]
    try:
        site_snap = await site.sample_public_snapshot()
    except Exception as exc:  # noqa: BLE001
        site_snap = {"ok": False, "error": str(exc)}
    widgets.append(
        {
            "key": "site_channel",
            "title": "کانال فروش سایت maahed.ir",
            "source": "maahed_site",
            "source_field": "سایت.وضعیت_عمومی / سفارش‌ها پس از ادمین",
            "freshness_label": site_status.get("freshness_label") or sales_as_of,
            "freshness_kind": "as_of",
            "sort_order": 2,
            "data": {"status": site_status, "snapshot": site_snap},
        }
    )

    # Finance baseline from Sepidar (connection + optional bank balances)
    finance_data: dict[str, Any] = {
        "connection": sepidar_status,
        "disclaimer": "عددها از منبع/فیلد خام سپیدار هستند؛ دفترچه تعریف مفاهیم فاز بعدی است",
    }
    finance_source = "سپیدار — فیلدهای خام حسابداری (بدون تعریف مفهوم هزینه/سود در این فاز)"
    if sepidar_status.get("configured") and sepidar_status.get("ok"):
        try:
            banks = await sepidar.sample_bank_accounts()
            bank_rows = _as_rows(banks)
            if bank_rows:
                finance_data["cash_banks"] = summarize_bank_accounts(bank_rows)
                finance_source = "سپیدار.get_bank_accounts (مانده خام)"
            else:
                finance_data["cash_banks"] = {"account_count": 0, "accounts": [], "note": "حساب بانکی برنگشت"}
        except Exception as exc:  # noqa: BLE001
            finance_data["cash_banks"] = {"ok": False, "error": str(exc)}

    widgets.append(
        {
            "key": "finance_baseline",
            "title": "داده مالی پایه",
            "source": "sepidar",
            "source_field": finance_source,
            "freshness_label": sepidar_status.get("freshness_label", "سپیدار"),
            "freshness_kind": "live",
            "sort_order": 3,
            "data": finance_data,
        }
    )

    if is_board:
        widgets.append(
            {
                "key": "board_framing",
                "title": "چارچوب گزارش هیئت‌مدیره",
                "source": "manual",
                "source_field": "درخواست کاربر",
                "freshness_label": f"تولید شده در {datetime.now(timezone.utc).isoformat()}",
                "freshness_kind": "generated",
                "sort_order": 0,
                "data": {
                    "request": text,
                    "audience": "هیئت‌مدیره / مدیرعامل",
                    "suggested_narrative": (
                        "خلاصه فروش و روند ماهانه + مانده بانکی خام + وضعیت کانال سایت — "
                        "برای تصمیم‌گیری هیئت‌مدیره؛ قابل اصلاح پس از مشاهده"
                    ),
                    "focus": ["درآمد/فروش", "نقدینگی (مانده بانکی خام)", "کانال سایت", "ریسک عملیاتی"],
                },
            }
        )
    elif is_investor:
        widgets.append(
            {
                "key": "investor_framing",
                "title": "چارچوب جلسه سرمایه‌گذار",
                "source": "manual",
                "source_field": "درخواست کاربر",
                "freshness_label": f"تولید شده در {datetime.now(timezone.utc).isoformat()}",
                "freshness_kind": "generated",
                "sort_order": 0,
                "data": {
                    "request": text,
                    "suggested_narrative": "رشد فروش + پایه مالی + کانال سایت — قابل اصلاح پس از مشاهده",
                },
            }
        )

    widgets.sort(key=lambda w: w["sort_order"])
    return widgets


async def create_dashboard_from_request(
    db: AsyncSession,
    request_text: str,
    created_by: str,
    sepidar: SepidarConnector,
    site: MaahedSiteConnector,
    title: str | None = None,
) -> Dashboard:
    widgets_spec = await propose_widgets(request_text, sepidar, site)
    dash = Dashboard(
        public_id=str(uuid.uuid4()),
        title=title or _default_title(request_text),
        request_text=request_text,
        status="proposed",
        created_by=created_by,
    )
    db.add(dash)
    await db.flush()
    for spec in widgets_spec:
        db.add(
            Widget(
                dashboard_id=dash.id,
                key=spec["key"],
                title=spec["title"],
                source=spec["source"],
                source_field=spec["source_field"],
                freshness_label=spec["freshness_label"],
                freshness_kind=spec["freshness_kind"],
                sort_order=spec["sort_order"],
                data=spec["data"],
            )
        )
    await db.commit()
    return await get_dashboard(db, dash.public_id)


async def revise_dashboard(
    db: AsyncSession,
    public_id: str,
    revision_notes: str,
    sepidar: SepidarConnector,
    site: MaahedSiteConnector,
) -> Dashboard:
    dash = await get_dashboard(db, public_id)
    if dash is None:
        raise ValueError("dashboard not found")
    combined = f"{dash.request_text}\n\n[اصلاح کاربر]: {revision_notes}".strip()
    dash.request_text = combined
    dash.revision_notes = (dash.revision_notes + "\n" + revision_notes).strip()
    dash.status = "revised"
    # Rebuild widgets
    for w in list(dash.widgets):
        await db.delete(w)
    await db.flush()
    for spec in await propose_widgets(combined, sepidar, site):
        db.add(
            Widget(
                dashboard_id=dash.id,
                key=spec["key"],
                title=spec["title"],
                source=spec["source"],
                source_field=spec["source_field"],
                freshness_label=spec["freshness_label"],
                freshness_kind=spec["freshness_kind"],
                sort_order=spec["sort_order"],
                data=spec["data"],
            )
        )
    await db.commit()
    return await get_dashboard(db, public_id)


async def publish_dashboard(db: AsyncSession, public_id: str) -> Dashboard:
    dash = await get_dashboard(db, public_id)
    if dash is None:
        raise ValueError("dashboard not found")
    dash.status = "published"
    await db.commit()
    return await get_dashboard(db, public_id)


async def get_dashboard(db: AsyncSession, public_id: str) -> Dashboard | None:
    result = await db.execute(
        select(Dashboard)
        .where(Dashboard.public_id == public_id)
        .options(selectinload(Dashboard.widgets))
    )
    return result.scalar_one_or_none()


def dashboard_to_dict(dash: Dashboard, public_base_url: str) -> dict[str, Any]:
    return {
        "id": dash.id,
        "public_id": dash.public_id,
        "title": dash.title,
        "request_text": dash.request_text,
        "status": dash.status,
        "revision_notes": dash.revision_notes,
        "created_by": dash.created_by,
        "url": f"{public_base_url.rstrip('/')}/d/{dash.public_id}",
        "widgets": [
            {
                "key": w.key,
                "title": w.title,
                "source": w.source,
                "source_field": w.source_field,
                "freshness_label": w.freshness_label,
                "freshness_kind": w.freshness_kind,
                "sort_order": w.sort_order,
                "data": w.data,
            }
            for w in sorted(dash.widgets, key=lambda x: x.sort_order)
        ],
    }


def _default_title(request_text: str) -> str:
    cleaned = re.sub(r"\s+", " ", request_text).strip()
    if len(cleaned) > 60:
        return cleaned[:57] + "…"
    return cleaned or "داشبورد جدید"
