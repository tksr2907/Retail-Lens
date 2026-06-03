"""
Heatmap computation: zone visit frequency + avg dwell, normalised 0-100.
"""

from typing import List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord
from app.models import HeatmapResponse, HeatmapZone
from app.metrics import get_today_window

MIN_SESSIONS_FOR_CONFIDENCE = 20


def compute_heatmap(store_id: str, db: Session) -> HeatmapResponse:
    start_ts, now_ts = get_today_window()

    def q():
        return db.query(EventRecord).filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.timestamp >= start_ts,
        )

    # Visit frequency per zone (ZONE_ENTER count)
    freq_rows = (
        q().filter(
            EventRecord.event_type == "ZONE_ENTER",
            EventRecord.zone_id.isnot(None),
        ).with_entities(
            EventRecord.zone_id,
            func.count(EventRecord.id),
        ).group_by(EventRecord.zone_id).all()
    )

    # Avg dwell per zone
    dwell_rows = (
        q().filter(
            EventRecord.event_type == "ZONE_DWELL",
            EventRecord.zone_id.isnot(None),
        ).with_entities(
            EventRecord.zone_id,
            func.avg(EventRecord.dwell_ms),
        ).group_by(EventRecord.zone_id).all()
    )
    dwell_map = {r[0]: float(r[1]) for r in dwell_rows}

    # Total unique sessions today (for confidence flag)
    total_sessions = (
        q().filter(EventRecord.event_type == "ENTRY")
        .with_entities(func.count(distinct(EventRecord.visitor_id)))
        .scalar() or 0
    )

    zones = []
    for zone_id, freq in freq_rows:
        avg_dwell = dwell_map.get(zone_id, 0.0)
        zones.append({
            "zone_id": zone_id,
            "visit_frequency": freq,
            "avg_dwell_ms": round(avg_dwell, 1),
        })

    # Normalise visit_frequency to 0-100
    max_freq = max((z["visit_frequency"] for z in zones), default=1)
    zone_objects = []
    for z in zones:
        score = round(z["visit_frequency"] / max_freq * 100, 1) if max_freq > 0 else 0.0
        zone_objects.append(HeatmapZone(
            zone_id=z["zone_id"],
            visit_frequency=z["visit_frequency"],
            avg_dwell_ms=z["avg_dwell_ms"],
            score=score,
            data_confidence=total_sessions >= MIN_SESSIONS_FOR_CONFIDENCE,
        ))

    return HeatmapResponse(
        store_id=store_id,
        as_of=now_ts,
        zones=zone_objects,
    )
