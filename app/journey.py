"""
Customer journey / zone-to-zone path analysis.

Answers: "Which zones do customers visit in sequence?
          Which paths lead to purchase vs exit?"
"""

from collections import Counter
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import EventRecord
from app.metrics import get_today_window


def compute_journey(store_id: str, db: Session) -> dict:
    start_ts, now_ts = get_today_window()

    # Get all ZONE_ENTER events per visitor, ordered by timestamp
    rows = (
        db.query(EventRecord.visitor_id, EventRecord.zone_id, EventRecord.timestamp)
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type == "ZONE_ENTER",
            EventRecord.zone_id.isnot(None),
            EventRecord.timestamp >= start_ts,
        )
        .order_by(EventRecord.visitor_id, EventRecord.timestamp)
        .all()
    )

    # Build per-visitor zone sequences
    visitor_paths: Dict[str, List[str]] = {}
    for vid, zone, ts in rows:
        if vid not in visitor_paths:
            visitor_paths[vid] = []
        if not visitor_paths[vid] or visitor_paths[vid][-1] != zone:
            visitor_paths[vid].append(zone)

    # Count full paths
    path_counter: Counter = Counter()
    for path in visitor_paths.values():
        path_counter[" → ".join(path)] += 1

    # Count zone-to-zone transitions
    transition_counter: Counter = Counter()
    for path in visitor_paths.values():
        for i in range(len(path) - 1):
            transition_counter[(path[i], path[i + 1])] += 1

    # Average zones visited per session
    avg_zones = (
        round(sum(len(p) for p in visitor_paths.values()) / len(visitor_paths), 2)
        if visitor_paths else 0.0
    )

    top_paths = [
        {"path": path, "count": count}
        for path, count in path_counter.most_common(10)
    ]

    top_transitions = [
        {"from_zone": t[0], "to_zone": t[1], "count": c}
        for t, c in transition_counter.most_common(10)
    ]

    return {
        "store_id": store_id,
        "as_of": now_ts,
        "total_sessions_with_zones": len(visitor_paths),
        "avg_zones_per_visit": avg_zones,
        "top_paths": top_paths,
        "top_transitions": top_transitions,
    }
