"""Real-time metric computation."""

from typing import List, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord
from app.models import StoreMetrics, ZoneDwell


def get_today_window(date_str: Optional[str] = None):
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            return day.strftime("%Y-%m-%dT00:00:00Z"), day.strftime("%Y-%m-%dT23:59:59Z")
        except Exception:
            pass
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%dT%H:%M:%SZ"), now.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_metrics(store_id: str, db: Session, date_str: Optional[str] = None) -> StoreMetrics:
    start_ts, now_ts = get_today_window(date_str)

    def q():
        return db.query(EventRecord).filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.timestamp >= start_ts,
        )

    unique_visitors = (
        q().filter(EventRecord.event_type == "ENTRY")
        .with_entities(func.count(distinct(EventRecord.visitor_id)))
        .scalar() or 0
    )

    billing_visitors = set(
        r[0] for r in q().filter(
            EventRecord.event_type.in_(["BILLING_QUEUE_JOIN", "ZONE_ENTER"]),
            EventRecord.zone_id == "BILLING",
        ).with_entities(EventRecord.visitor_id).all()
    )
    abandon_visitors = set(
        r[0] for r in q().filter(EventRecord.event_type == "BILLING_QUEUE_ABANDON")
        .with_entities(EventRecord.visitor_id).all()
    )
    converted = len(billing_visitors - abandon_visitors)
    conversion_rate = round(converted / unique_visitors, 4) if unique_visitors > 0 else 0.0

    avg_dwell_row = (
        q().filter(EventRecord.event_type == "ZONE_DWELL")
        .with_entities(func.avg(EventRecord.dwell_ms)).scalar()
    )
    avg_dwell_ms = round(float(avg_dwell_row), 1) if avg_dwell_row else 0.0

    recent_billing = q().filter(
        EventRecord.event_type == "BILLING_QUEUE_JOIN",
        EventRecord.timestamp >= (
            datetime.now(timezone.utc) - timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    ).count()
    queue_depth = max(0, recent_billing)

    total_billing_joins = q().filter(EventRecord.event_type == "BILLING_QUEUE_JOIN").count()
    total_abandons = q().filter(EventRecord.event_type == "BILLING_QUEUE_ABANDON").count()
    abandonment_rate = round(total_abandons / total_billing_joins, 4) if total_billing_joins > 0 else 0.0

    zone_rows = (
        q().filter(EventRecord.event_type == "ZONE_DWELL", EventRecord.zone_id.isnot(None))
        .with_entities(EventRecord.zone_id, func.avg(EventRecord.dwell_ms), func.count(EventRecord.id))
        .group_by(EventRecord.zone_id).all()
    )
    zone_dwells = [
        ZoneDwell(zone_id=r[0], avg_dwell_ms=round(float(r[1]), 1), visit_count=r[2])
        for r in zone_rows
    ]

    return StoreMetrics(
        store_id=store_id,
        as_of=now_ts,
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_ms=avg_dwell_ms,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
        zone_dwells=zone_dwells,
    )
