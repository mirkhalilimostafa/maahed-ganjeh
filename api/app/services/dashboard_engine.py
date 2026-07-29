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


INVESTOR_KEYWORDS = ("سرمایه", "سرمایه\u200cگذار", "investor", "جلسه", "رشد", "عملکرد")


def _jalali_approx_label(d: date) -> str:
    # Lightweight Gregorian label; UI can show as-is. Full Jalali conversion can come later.
    return d.isoformat()


async def propose_widgets(
    request_text: str,
    sepidar: SepidarConnector,
    site: MaahedSiteConnector,
) -> list[dict[str, Any]]:
    """Rule-based propose for v0 (NL → component list). LLM can replace later without API change."""
    text = request_text.strip()
    lower = text.lower()
    is_investor = any(k in text or k in lower for k in INVESTOR_KEYWORDS)

    sepidar_status = await sepidar.status()
    site_status = await site.status()

    today = date.today()
    from_date = (today - timedelta(days=90)).isoformat()
    to_date = today.isoformat()
    sales_as_of = site_status.get("freshness_label") or f"داده فروش تا تاریخ {_jalali_approx_label(today - timedelta(days=5))}"

    widgets: list[dict[str, Any]] = []

    # Sales growth / performance
    sales_payload: dict[str, Any] = {
        "period": {"from": from_date, "to": to_date},
        "note": "منبع خام فروش — بدون یکسان‌سازی مفهومی",
    }
    if sepidar_status.get("configured") and sepidar_status.get("ok"):
        sample = await sepidar.sample_sales_review(from_date, to_date)
        sales_payload["sepidar_sales_review"] = sample
        sales_source_field = "سپیدار.get_sales_review"
        sales_freshness = sepidar_status.get("freshness_label", "داده مالی سپیدار: به‌روز لحظه‌ای")
    else:
        sales_payload["sepidar_sales_review"] = {"ok": False, "detail": sepidar_status.get("detail")}
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

    # Finance baseline from Sepidar
    widgets.append(
        {
            "key": "finance_baseline",
            "title": "داده مالی پایه",
            "source": "sepidar",
            "source_field": "سپیدار — فیلدهای خام حسابداری (بدون تعریف مفهوم هزینه/سود در این فاز)",
            "freshness_label": sepidar_status.get("freshness_label", "سپیدار"),
            "freshness_kind": "live",
            "sort_order": 3,
            "data": {
                "connection": sepidar_status,
                "disclaimer": "عددها از منبع/فیلد خام سپیدار هستند؛ دفترچه تعریف مفاهیم فاز بعدی است",
            },
        }
    )

    if is_investor:
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
