"""
Revenue and basket value analytics endpoint.
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord
from app.pos import get_confirmed_purchases, load_pos_transactions
from app.metrics import get_today_window


def compute_revenue(store_id: str, db: Session, date_str: Optional[str] = None) -> dict:
    start_ts, now_ts = get_today_window()
    try:
        pos_data = get_confirmed_purchases(store_id, db, date_str)
    except Exception:
        pos_data = None
    if pos_data is None:
        pos_data = {"total_gmv_inr":0.0,"total_nmv_inr":0.0,"total_transactions":0,
                    "avg_basket_value_inr":0.0,"confirmed_purchases":0,"correlation_window_minutes":5}

    # Unique visitors today
    unique_visitors = (
        db.query(func.count(distinct(EventRecord.visitor_id)))
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type == "ENTRY",
            EventRecord.timestamp >= start_ts,
        )
        .scalar() or 0
    )

    revenue_per_visitor = (
        round(pos_data["total_gmv_inr"] / unique_visitors, 2)
        if unique_visitors > 0 else 0.0
    )

    # Top zone by dwell (proxy for product interest)
    top_zone_row = (
        db.query(EventRecord.zone_id, func.avg(EventRecord.dwell_ms))
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type == "ZONE_DWELL",
            EventRecord.zone_id.isnot(None),
            EventRecord.timestamp >= start_ts,
        )
        .group_by(EventRecord.zone_id)
        .order_by(func.avg(EventRecord.dwell_ms).desc())
        .first()
    )

    return {
        "store_id": store_id,
        "as_of": now_ts,
        "total_gmv_inr": pos_data["total_gmv_inr"],
        "total_nmv_inr": pos_data["total_nmv_inr"],
        "total_transactions": pos_data["total_transactions"],
        "avg_basket_value_inr": pos_data["avg_basket_value_inr"],
        "confirmed_purchases": pos_data["confirmed_purchases"],
        "unique_visitors": unique_visitors,
        "revenue_per_visitor_inr": revenue_per_visitor,
        "top_dwell_zone": top_zone_row[0] if top_zone_row else None,
        "conversion_rate_pos": round(
            pos_data["confirmed_purchases"] / unique_visitors, 4
        ) if unique_visitors > 0 else 0.0,
    }
