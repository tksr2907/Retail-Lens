"""
Hourly traffic analysis — when is the store busiest?
"""

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord
from app.metrics import get_today_window


def compute_hourly(store_id: str, db: Session, date_str: Optional[str] = None) -> dict:
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = day.strftime("%Y-%m-%dT00:00:00Z")
            end_ts = day.strftime("%Y-%m-%dT23:59:59Z")
        except Exception:
            start_ts, end_ts = get_today_window()
    else:
        start_ts, end_ts = get_today_window()

    rows = (
        db.query(EventRecord.timestamp, EventRecord.visitor_id)
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type == "ENTRY",
            EventRecord.timestamp >= start_ts,
        )
        .all()
    )

    hourly = {}
    for ts_str, vid in rows:
        try:
            hour = ts_str[11:13]
            key = f"{hour}:00"
            hourly[key] = hourly.get(key, 0) + 1
        except Exception:
            continue

    all_hours = {f"{h:02d}:00": hourly.get(f"{h:02d}:00", 0) for h in range(0, 24)}

    if any(all_hours.values()):
        peak_hour = max(all_hours, key=lambda k: (all_hours[k], 10 <= int(k[:2]) <= 22))
    else:
        peak_hour = "10:00"

    total = sum(all_hours.values())

    return {
        "store_id": store_id,
        "date": date_str or start_ts[:10],
        "peak_hour": peak_hour,
        "total_visitors": total,
        "hourly_visitors": all_hours,
    }
