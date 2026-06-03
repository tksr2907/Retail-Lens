"""
Anomaly detection engine.

Detected anomaly types:
- BILLING_QUEUE_SPIKE  : queue_depth > threshold in recent window
- CONVERSION_DROP      : today's conversion < 7-day avg by > 20%
- DEAD_ZONE            : no zone visits in 30 min for a non-empty store
- STALE_CAMERA_FEED    : no events from a camera in 10+ minutes
- HIGH_ABANDONMENT_RATE: billing queue abandon rate > 40%

Severity mapping:
- BILLING_QUEUE_SPIKE  : WARN (>5 in queue) / CRITICAL (>10)
- CONVERSION_DROP      : WARN (>20% drop) / CRITICAL (>50% drop)
- DEAD_ZONE            : INFO (single zone) / WARN (multiple zones)
- STALE_CAMERA_FEED    : WARN
- HIGH_ABANDONMENT_RATE: WARN (>40%) / CRITICAL (>60%)
"""

import uuid
from typing import List
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord
from app.models import Anomaly, AnomalyResponse
from app.metrics import get_today_window, compute_metrics


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts_minutes_ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def detect_anomalies(store_id: str, db: Session) -> AnomalyResponse:
    anomalies: List[Anomaly] = []
    start_ts, now_ts = get_today_window()
    as_of = now_ts

    def q():
        return db.query(EventRecord).filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
        )

    # -------------------------------------------------------
    # 1. BILLING QUEUE SPIKE
    # -------------------------------------------------------
    billing_count_recent = (
        q().filter(
            EventRecord.event_type == "BILLING_QUEUE_JOIN",
            EventRecord.timestamp >= _ts_minutes_ago(10),
        ).count()
    )
    if billing_count_recent > 10:
        anomalies.append(Anomaly(
            anomaly_id=str(uuid.uuid4()),
            anomaly_type="BILLING_QUEUE_SPIKE",
            severity="CRITICAL",
            description=f"Billing queue has {billing_count_recent} visitors — critical buildup.",
            suggested_action="Open additional billing counters immediately.",
            detected_at=_now_ts(),
            store_id=store_id,
            zone_id="BILLING",
            value=float(billing_count_recent),
            threshold=10.0,
        ))
    elif billing_count_recent > 5:
        anomalies.append(Anomaly(
            anomaly_id=str(uuid.uuid4()),
            anomaly_type="BILLING_QUEUE_SPIKE",
            severity="WARN",
            description=f"Billing queue at {billing_count_recent} visitors — above normal.",
            suggested_action="Alert floor manager. Consider routing customers to adjacent counter.",
            detected_at=_now_ts(),
            store_id=store_id,
            zone_id="BILLING",
            value=float(billing_count_recent),
            threshold=5.0,
        ))

    # -------------------------------------------------------
    # 2. CONVERSION DROP (vs 7-day avg)
    # -------------------------------------------------------
    today_conv = 0.0
    try:
        metrics = compute_metrics(store_id, db)
        today_conv = metrics.conversion_rate
    except Exception:
        pass

    seven_day_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hist_entry = (
        q().filter(EventRecord.event_type == "ENTRY",
                   EventRecord.timestamp >= seven_day_start,
                   EventRecord.timestamp < start_ts)
        .with_entities(func.count(distinct(EventRecord.visitor_id))).scalar() or 0
    )
    hist_billing = (
        q().filter(EventRecord.event_type.in_(["BILLING_QUEUE_JOIN", "ZONE_ENTER"]),
                   EventRecord.zone_id == "BILLING",
                   EventRecord.timestamp >= seven_day_start,
                   EventRecord.timestamp < start_ts)
        .with_entities(func.count(distinct(EventRecord.visitor_id))).scalar() or 0
    )
    hist_conv = hist_billing / hist_entry if hist_entry > 0 else None

    if hist_conv and hist_conv > 0:
        drop_pct = (hist_conv - today_conv) / hist_conv * 100
        if drop_pct > 50:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="CONVERSION_DROP",
                severity="CRITICAL",
                description=f"Conversion rate {today_conv:.1%} vs 7-day avg {hist_conv:.1%} — {drop_pct:.0f}% drop.",
                suggested_action="Check billing systems, promotions, and staff coverage immediately.",
                detected_at=_now_ts(), store_id=store_id, value=today_conv, threshold=hist_conv * 0.5,
            ))
        elif drop_pct > 20:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="CONVERSION_DROP",
                severity="WARN",
                description=f"Conversion rate {today_conv:.1%} vs 7-day avg {hist_conv:.1%} — {drop_pct:.0f}% below average.",
                suggested_action="Review promotions and floor staff. Monitor for 30 min.",
                detected_at=_now_ts(), store_id=store_id, value=today_conv, threshold=hist_conv * 0.8,
            ))

    # -------------------------------------------------------
    # 3. DEAD ZONE (no visits in last 30 min)
    # -------------------------------------------------------
    recent_zone_visits = (
        q().filter(EventRecord.event_type.in_(["ZONE_ENTER", "ZONE_DWELL"]),
                   EventRecord.timestamp >= _ts_minutes_ago(30),
                   EventRecord.zone_id.isnot(None))
        .with_entities(distinct(EventRecord.zone_id)).all()
    )
    active_zones = {r[0] for r in recent_zone_visits}

    has_traffic = q().filter(
        EventRecord.event_type == "ENTRY",
        EventRecord.timestamp >= start_ts,
    ).count() > 0

    if has_traffic:
        all_zone_rows = (
            q().filter(EventRecord.event_type.in_(["ZONE_ENTER"]),
                       EventRecord.timestamp >= start_ts,
                       EventRecord.zone_id.isnot(None),
                       EventRecord.zone_id != "BILLING")
            .with_entities(distinct(EventRecord.zone_id)).all()
        )
        all_zones_today = {r[0] for r in all_zone_rows}
        dead_zones = all_zones_today - active_zones - {"ENTRY", "BILLING"}

        for zone in dead_zones:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="DEAD_ZONE",
                severity="WARN" if len(dead_zones) > 2 else "INFO",
                description=f"Zone {zone} has had no customer visits in 30 minutes.",
                suggested_action=f"Check product availability and staff presence in {zone}.",
                detected_at=_now_ts(), store_id=store_id, zone_id=zone,
            ))

    # -------------------------------------------------------
    # 4. STALE CAMERA FEED (no events from a camera in 10+ min)
    # -------------------------------------------------------
    if has_traffic:
        active_cameras = set(
            r[0] for r in db.query(EventRecord.camera_id)
            .filter(EventRecord.store_id == store_id,
                    EventRecord.timestamp >= _ts_minutes_ago(10))
            .distinct().all()
        )
        all_cameras = set(
            r[0] for r in db.query(EventRecord.camera_id)
            .filter(EventRecord.store_id == store_id,
                    EventRecord.timestamp >= start_ts)
            .distinct().all()
        )
        for cam in (all_cameras - active_cameras):
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="STALE_CAMERA_FEED",
                severity="WARN",
                description=f"Camera {cam} has sent no events in the last 10 minutes.",
                suggested_action=f"Check camera {cam} connectivity and power supply.",
                detected_at=_now_ts(), store_id=store_id,
            ))

    # -------------------------------------------------------
    # 5. HIGH ABANDONMENT RATE (>40% billing queue abandon)
    # -------------------------------------------------------
    total_joins = q().filter(EventRecord.event_type == "BILLING_QUEUE_JOIN",
                             EventRecord.timestamp >= start_ts).count()
    total_abandons = q().filter(EventRecord.event_type == "BILLING_QUEUE_ABANDON",
                                EventRecord.timestamp >= start_ts).count()
    if total_joins >= 5:
        rate = total_abandons / total_joins
        if rate > 0.6:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="HIGH_ABANDONMENT_RATE",
                severity="CRITICAL",
                description=f"Billing abandonment at {rate:.0%} ({total_abandons}/{total_joins}) — customers leaving without purchase.",
                suggested_action="Open additional billing counters immediately.",
                detected_at=_now_ts(), store_id=store_id, zone_id="BILLING",
                value=round(rate, 4), threshold=0.6,
            ))
        elif rate > 0.4:
            anomalies.append(Anomaly(
                anomaly_id=str(uuid.uuid4()),
                anomaly_type="HIGH_ABANDONMENT_RATE",
                severity="WARN",
                description=f"Billing abandonment at {rate:.0%} ({total_abandons}/{total_joins}) — above normal.",
                suggested_action="Monitor billing zone. Alert floor manager if trend continues.",
                detected_at=_now_ts(), store_id=store_id, zone_id="BILLING",
                value=round(rate, 4), threshold=0.4,
            ))

    return AnomalyResponse(store_id=store_id, as_of=as_of, anomalies=anomalies)
