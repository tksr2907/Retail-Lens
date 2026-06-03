"""
Health endpoint — what an on-call engineer checks first.

Reports:
- Service uptime
- Last event timestamp per store
- STALE_FEED warning if any store has > 10 min lag since last event
- DEGRADED only after 8+ hours silence (store closed / pipeline down)
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import EventRecord
from app.models import HealthResponse, StoreHealth

STALE_FEED_THRESHOLD_MINUTES = 10   # per-store STALE_FEED warning threshold
STALE_FEED_DEGRADED_MINUTES = 480   # overall DEGRADED only after 8h silence


def compute_health(db: Session) -> HealthResponse:
    now = datetime.now(timezone.utc)
    now_ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    store_rows = db.query(EventRecord.store_id).distinct().all()
    stores = [r[0] for r in store_rows]

    store_healths = []
    overall_status = "OK"

    for store_id in stores:
        last_event_row = (
            db.query(func.max(EventRecord.timestamp))
            .filter(EventRecord.store_id == store_id)
            .scalar()
        )
        if last_event_row is None:
            store_healths.append(StoreHealth(
                store_id=store_id,
                status="NO_DATA",
                last_event_at=None,
                lag_minutes=None,
            ))
            overall_status = "DEGRADED"
            continue

        try:
            last_event_dt = datetime.fromisoformat(last_event_row.replace("Z", "+00:00"))
            lag = (now - last_event_dt).total_seconds() / 60
        except Exception:
            lag = None

        if lag is not None and lag > STALE_FEED_DEGRADED_MINUTES:
            status = "STALE_FEED"
            overall_status = "DEGRADED"
        elif lag is not None and lag > STALE_FEED_THRESHOLD_MINUTES:
            status = "STALE_FEED"  # per-store warning; service overall stays OK
        else:
            status = "OK"

        store_healths.append(StoreHealth(
            store_id=store_id,
            status=status,
            last_event_at=last_event_row,
            lag_minutes=round(lag, 2) if lag is not None else None,
        ))

    if not stores:
        store_healths.append(StoreHealth(
            store_id="NO_STORES",
            status="NO_DATA",
            last_event_at=None,
            lag_minutes=None,
        ))
        overall_status = "DEGRADED"

    return HealthResponse(
        status=overall_status,
        service="store-intelligence-api",
        version="1.0.0",
        as_of=now_ts,
        stores=store_healths,
    )
