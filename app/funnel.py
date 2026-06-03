"""
Conversion funnel computation.

Funnel stages:
  1. Entry    → total unique visitors (ENTRY events, deduplicated — REENTRY does NOT add new session)
  2. Zone Visit → visitors who triggered at least one ZONE_ENTER
  3. Billing Queue → visitors who reached BILLING zone
  4. Purchase → visitors in BILLING who did NOT abandon (proxy for purchase)

Session deduplication: REENTRY events link to same visitor_id, so
distinct(visitor_id) on ENTRY events already handles this correctly.
"""

from typing import List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import EventRecord
from app.models import FunnelResponse, FunnelStage
from app.metrics import get_today_window


def compute_funnel(store_id: str, db: Session) -> FunnelResponse:
    start_ts, now_ts = get_today_window()
    as_of = now_ts

    def q():
        return db.query(EventRecord).filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.timestamp >= start_ts,
        )

    # Stage 1: unique visitors who entered
    entry_visitors = set(
        r[0] for r in
        q().filter(EventRecord.event_type == "ENTRY")
        .with_entities(EventRecord.visitor_id).all()
    )
    n_entry = len(entry_visitors)

    # Stage 2: visitors with at least one zone visit
    zone_visitors = set(
        r[0] for r in
        q().filter(EventRecord.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]))
        .with_entities(EventRecord.visitor_id).all()
    ) & entry_visitors
    n_zone = len(zone_visitors)

    # Stage 3: visitors who reached billing
    billing_visitors = set(
        r[0] for r in
        q().filter(
            EventRecord.event_type.in_(["BILLING_QUEUE_JOIN", "ZONE_ENTER"]),
            EventRecord.zone_id == "BILLING",
        ).with_entities(EventRecord.visitor_id).all()
    ) & entry_visitors
    n_billing = len(billing_visitors)

    # Stage 4: purchased (billing - abandons)
    abandon_visitors = set(
        r[0] for r in
        q().filter(EventRecord.event_type == "BILLING_QUEUE_ABANDON")
        .with_entities(EventRecord.visitor_id).all()
    )
    purchased = billing_visitors - abandon_visitors
    n_purchased = len(purchased)

    def drop(a: int, b: int) -> float:
        if a == 0:
            return 0.0
        return round((a - b) / a * 100, 2)

    stages = [
        FunnelStage(stage="Entry", count=n_entry, drop_off_pct=drop(n_entry, n_zone)),
        FunnelStage(stage="Zone Visit", count=n_zone, drop_off_pct=drop(n_zone, n_billing)),
        FunnelStage(stage="Billing Queue", count=n_billing, drop_off_pct=drop(n_billing, n_purchased)),
        FunnelStage(stage="Purchase", count=n_purchased, drop_off_pct=0.0),
    ]

    return FunnelResponse(
        store_id=store_id,
        as_of=as_of,
        stages=stages,
        total_sessions=n_entry,
    )
