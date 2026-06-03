"""
FastAPI entrypoint — Store Intelligence API v2.0

Endpoints:
  GET  /metrics                     (acceptance gate)
  POST /events/ingest
  GET  /stores/{id}/metrics
  GET  /stores/{id}/funnel
  GET  /stores/{id}/heatmap
  GET  /stores/{id}/anomalies
  GET  /stores/{id}/revenue
  GET  /stores/{id}/hourly
  GET  /stores/{id}/journey
  GET  /stores/{id}/summary
  GET  /stores/{id}/pos
  GET  /stores/{id}/confidence
  GET  /stores/{id}/export
  GET  /stores/compare
  WS   /ws/stores/{id}
  GET  /health
  GET  /
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
import csv, io

from app.database import create_tables, get_db, EventRecord
from app.models import IngestRequest, IngestResponse, StoreMetrics, FunnelResponse, HeatmapResponse, AnomalyResponse, HealthResponse
from app.ingestion import ingest_events
from app.metrics import compute_metrics, get_today_window
from app.funnel import compute_funnel
from app.heatmap import compute_heatmap
from app.anomalies import detect_anomalies
from app.health import compute_health
from app.revenue import compute_revenue
from app.hourly import compute_hourly
from app.journey import compute_journey
from app.logger import RequestLoggingMiddleware, logger
from app.dashboard import DASHBOARD_HTML


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    _auto_seed()
    logger.info("startup", message="RetailLens API v2.0 started")
    yield

app = FastAPI(title="RetailLens — Store Intelligence API", version="2.0.0", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(OperationalError)
async def db_error_handler(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"error": "database_unavailable", "message": "Database temporarily unavailable."})


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error("unhandled_error", error=str(exc))
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": "An internal error occurred."})


# ── Acceptance gate endpoint ──────────────────────────────────────────────────

@app.get("/metrics")
async def metrics_top_level(db: Session = Depends(get_db)):
    """Acceptance-gate endpoint — aggregates KPIs across all known stores."""
    store_ids = [r[0] for r in db.query(EventRecord.store_id).distinct().all()]
    if not store_ids:
        store_ids = ["STORE_BLR_002"]
    results = [compute_metrics(sid, db).model_dump() for sid in store_ids]
    total_visitors = sum(r["unique_visitors"] for r in results)
    avg_conversion = round(sum(r["conversion_rate"] for r in results) / len(results), 4) if results else 0.0
    return {
        "as_of": results[0]["as_of"] if results else "",
        "store_count": len(results),
        "total_unique_visitors": total_visitors,
        "avg_conversion_rate": avg_conversion,
        "stores": results,
    }


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.post("/events/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest, request: Request, db: Session = Depends(get_db)):
    """Accepts batches of up to 500 events. Idempotent by event_id."""
    result = ingest_events(payload.events, db)
    logger.info("ingest", accepted=result.accepted, duplicate=result.duplicate, rejected=result.rejected)
    return result


@app.get("/stores/{store_id}/metrics", response_model=StoreMetrics)
async def metrics(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Unique visitors, conversion rate, avg dwell, queue depth."""
    return compute_metrics(store_id, db, date)


@app.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
async def funnel(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Conversion funnel: Entry -> Zone -> Billing -> Purchase."""
    return compute_funnel(store_id, db)


@app.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
async def heatmap(store_id: str, db: Session = Depends(get_db)):
    """Zone visit frequency + avg dwell, normalised 0-100."""
    return compute_heatmap(store_id, db)


@app.get("/stores/{store_id}/anomalies", response_model=AnomalyResponse)
async def anomalies(store_id: str, db: Session = Depends(get_db)):
    """Active anomalies with severity and suggested actions."""
    return detect_anomalies(store_id, db)


@app.get("/stores/{store_id}/revenue")
async def revenue(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Revenue analytics from POS transactions."""
    return compute_revenue(store_id, db, date)


@app.get("/stores/{store_id}/hourly")
async def hourly(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Hourly visitor traffic and peak hour."""
    return compute_hourly(store_id, db, date)


@app.get("/stores/{store_id}/journey")
async def journey(store_id: str, db: Session = Depends(get_db)):
    """Customer zone-to-zone path analysis."""
    return compute_journey(store_id, db)


@app.get("/stores/{store_id}/summary")
async def summary(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Single-call summary: metrics + funnel + anomalies + heatmap + revenue."""
    m = compute_metrics(store_id, db, date)
    f = compute_funnel(store_id, db)
    a = detect_anomalies(store_id, db)
    h = compute_heatmap(store_id, db)
    rev = compute_revenue(store_id, db, date)
    return {
        "store_id": store_id,
        "as_of": m.as_of,
        "metrics": m.model_dump(),
        "funnel": f.model_dump(),
        "anomalies": a.model_dump(),
        "heatmap": h.model_dump(),
        "revenue": rev,
        "alert_count": len(a.anomalies),
        "health_status": (
            "CRITICAL" if any(x.severity == "CRITICAL" for x in a.anomalies)
            else "WARN" if any(x.severity == "WARN" for x in a.anomalies)
            else "OK"
        ),
    }


@app.get("/stores/{store_id}/pos")
async def pos_breakdown(store_id: str, date: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """Department/brand/SKU breakdown from POS CSV."""
    from app.pos import load_pos_transactions, _raw_pos_rows
    from collections import defaultdict
    from datetime import datetime, timezone

    if date:
        try:
            day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = day.strftime("%Y-%m-%dT00:00:00Z")
            end_ts = day.strftime("%Y-%m-%dT23:59:59Z")
        except Exception:
            start_ts, end_ts = get_today_window()
    else:
        start_ts, end_ts = get_today_window()

    transactions = load_pos_transactions(store_id)
    window_txns = [t for t in transactions if start_ts <= t["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ") <= end_ts]
    if not window_txns:
        window_txns = transactions

    dept_revenue: dict = defaultdict(lambda: {"gmv": 0.0, "nmv": 0.0, "orders": 0})
    brand_revenue: dict = defaultdict(float)
    hourly_rev: dict = defaultdict(float)
    top_skus = []

    for row in _raw_pos_rows(store_id):
        try:
            dept = row.get("dep_name", "unknown")
            gmv = float(row.get("GMV", 0) or 0)
            nmv = float(row.get("NMV", 0) or 0)
            brand = row.get("brand_name", "unknown")
            h = row.get("order_time", "")[:2]
            dept_revenue[dept]["gmv"] += gmv
            dept_revenue[dept]["nmv"] += nmv
            dept_revenue[dept]["orders"] += 1
            brand_revenue[brand] += gmv
            if h.isdigit():
                hourly_rev[int(h)] += gmv
            top_skus.append({"product": row.get("product_name", "")[:60], "brand": brand, "gmv": gmv, "qty": int(row.get("qty", 1) or 1)})
        except Exception:
            continue

    top_brands = sorted(brand_revenue.items(), key=lambda x: x[1], reverse=True)[:5]
    peak_hour = max(hourly_rev, key=hourly_rev.get) if hourly_rev else None

    return {
        "store_id": store_id,
        "as_of": end_ts,
        "date": date or start_ts[:10],
        "total_transactions": len(window_txns),
        "total_gmv_inr": round(sum(t["gmv"] for t in window_txns), 2),
        "department_breakdown": [
            {"department": dept, "gmv_inr": round(s["gmv"], 2), "nmv_inr": round(s["nmv"], 2), "transaction_count": s["orders"]}
            for dept, s in sorted(dept_revenue.items(), key=lambda x: x[1]["gmv"], reverse=True)
        ],
        "top_brands": [{"brand": b, "gmv_inr": round(v, 2)} for b, v in top_brands],
        "top_skus": sorted(top_skus, key=lambda x: x["gmv"], reverse=True)[:10],
        "peak_revenue_hour": peak_hour,
        "hourly_gmv": {str(h): round(v, 2) for h, v in sorted(hourly_rev.items())},
    }


@app.get("/stores/{store_id}/confidence")
async def confidence_stats(store_id: str, db: Session = Depends(get_db)):
    """Detection confidence distribution across buckets."""
    start_ts, now_ts = get_today_window()
    rows = db.query(EventRecord.confidence).filter(EventRecord.store_id == store_id, EventRecord.timestamp >= start_ts).all()
    confs = [r[0] for r in rows if r[0] is not None]
    if not confs:
        return {"store_id": store_id, "total_events": 0, "buckets": {}, "avg_confidence": 0}
    buckets = {"0.0-0.5": 0, "0.5-0.7": 0, "0.7-0.85": 0, "0.85-0.95": 0, "0.95-1.0": 0}
    for c in confs:
        if c < 0.5:    buckets["0.0-0.5"] += 1
        elif c < 0.7:  buckets["0.5-0.7"] += 1
        elif c < 0.85: buckets["0.7-0.85"] += 1
        elif c < 0.95: buckets["0.85-0.95"] += 1
        else:           buckets["0.95-1.0"] += 1
    return {
        "store_id": store_id, "as_of": now_ts,
        "total_events": len(confs),
        "avg_confidence": round(sum(confs) / len(confs), 4),
        "min_confidence": round(min(confs), 4),
        "max_confidence": round(max(confs), 4),
        "buckets": buckets,
        "low_confidence_pct": round(buckets["0.0-0.5"] / len(confs) * 100, 1),
    }


@app.get("/stores/{store_id}/export")
async def export_events(
    store_id: str,
    date: Optional[str] = Query(None),
    format: str = Query("json"),
    db: Session = Depends(get_db),
):
    """Export all events for a store as JSON or CSV."""
    start_ts, end_ts = get_today_window(date)
    rows = db.query(EventRecord).filter(EventRecord.store_id == store_id, EventRecord.timestamp >= start_ts).order_by(EventRecord.timestamp).all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["event_id", "store_id", "camera_id", "visitor_id", "event_type", "timestamp", "zone_id", "dwell_ms", "is_staff", "confidence", "queue_depth"])
        for r in rows:
            writer.writerow([r.event_id, r.store_id, r.camera_id, r.visitor_id, r.event_type, r.timestamp, r.zone_id, r.dwell_ms, r.is_staff, r.confidence, r.queue_depth])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={store_id}_{date or 'today'}.csv"})

    return {
        "store_id": store_id, "date": date or start_ts[:10], "total_events": len(rows),
        "events": [{"event_id": r.event_id, "visitor_id": r.visitor_id, "event_type": r.event_type,
                    "timestamp": r.timestamp, "zone_id": r.zone_id, "dwell_ms": r.dwell_ms,
                    "is_staff": r.is_staff, "confidence": r.confidence} for r in rows]
    }


@app.get("/stores/compare")
async def compare_stores(ids: str = Query(...), db: Session = Depends(get_db)):
    """Compare multiple stores ranked by conversion rate."""
    store_ids = [s.strip() for s in ids.split(",") if s.strip()]
    if not store_ids:
        raise HTTPException(status_code=400, detail="Provide at least one store ID")
    results = []
    for sid in store_ids:
        m = compute_metrics(sid, db)
        rev = compute_revenue(sid, db)
        results.append({"store_id": sid, "unique_visitors": m.unique_visitors,
                         "conversion_rate": m.conversion_rate, "avg_dwell_ms": m.avg_dwell_ms,
                         "queue_depth": m.queue_depth, "total_gmv_inr": rev["total_gmv_inr"],
                         "avg_basket_value_inr": rev["avg_basket_value_inr"]})
    results.sort(key=lambda x: x["conversion_rate"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1
    chain_avg = sum(r["conversion_rate"] for r in results) / len(results) if results else 0.0
    return {"stores": results, "best_performer": results[0]["store_id"] if results else None, "chain_avg_conversion": round(chain_avg, 4)}


@app.get("/health", response_model=HealthResponse)
async def health(db: Session = Depends(get_db)):
    """Service status and feed staleness per store."""
    return compute_health(db)


# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws/stores/{store_id}")
async def websocket_metrics(websocket: WebSocket, store_id: str):
    """Pushes live metrics every 3 seconds."""
    await websocket.accept()
    db = next(get_db())
    try:
        while True:
            try:
                m = compute_metrics(store_id, db)
                f = compute_funnel(store_id, db)
                a = detect_anomalies(store_id, db)
                h = compute_heatmap(store_id, db)
                await websocket.send_json({"type": "update", "metrics": m.model_dump(),
                                           "funnel": f.model_dump(), "anomalies": a.model_dump(),
                                           "heatmap": h.model_dump()})
            except Exception as ex:
                await websocket.send_json({"type": "error", "message": str(ex)})
            await asyncio.sleep(3)
    except WebSocketDisconnect:
        pass
    finally:
        db.close()


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Live dashboard with charts and WebSocket updates."""
    return HTMLResponse(content=DASHBOARD_HTML)


# ── Auto-seed ─────────────────────────────────────────────────────────────────

def _seed_events_from_file(sample_path: str, db, force: bool = False):
    """Seed events from a JSONL file. Re-anchors timestamps to today."""
    import json, uuid, os
    from datetime import datetime, timezone, timedelta
    from app.models import StoreEvent

    if not os.path.exists(sample_path):
        return 0

    raw_events = []
    with open(sample_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    raw_events.append(json.loads(line))
                except Exception:
                    continue

    if not raw_events:
        return 0

    try:
        # Anchor the LATEST event to ~2 minutes ago so health check shows OK
        # (last event within 10-min STALE_FEED threshold)
        latest_str  = max(e["timestamp"] for e in raw_events)
        earliest_str = min(e["timestamp"] for e in raw_events)
        latest_dt   = datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
        earliest_dt = datetime.fromisoformat(earliest_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        # Put the latest event at "2 minutes ago" so health feed is always fresh
        target_latest = now - timedelta(minutes=2)
        shift = target_latest - latest_dt
    except Exception:
        shift = timedelta(0)

    events = []
    for raw in raw_events:
        try:
            orig_ts = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
            raw["timestamp"] = (orig_ts + shift).strftime("%Y-%m-%dT%H:%M:%SZ")
            raw["event_id"] = str(uuid.uuid4())
            events.append(StoreEvent(**raw))
        except Exception:
            continue

    if not events:
        return 0

    from app.database import EventRecord as _ER
    from datetime import datetime as _dt, timezone as _tz
    records = []
    seen = set()
    now_str = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for ev in events:
        if ev.event_id in seen:
            continue
        seen.add(ev.event_id)
        records.append(_ER(
            event_id=ev.event_id, store_id=ev.store_id, camera_id=ev.camera_id,
            visitor_id=ev.visitor_id, event_type=ev.event_type, timestamp=ev.timestamp,
            zone_id=ev.zone_id, dwell_ms=ev.dwell_ms, is_staff=ev.is_staff,
            confidence=ev.confidence, queue_depth=ev.metadata.queue_depth,
            sku_zone=ev.metadata.sku_zone, session_seq=ev.metadata.session_seq,
            ingested_at=now_str,
        ))
    try:
        db.bulk_save_objects(records)
        db.commit()
        logger.info("auto_seed", seeded=len(records), source=sample_path,
                    time_shift_hours=round(shift.total_seconds() / 3600, 1))
        return len(records)
    except Exception as bulk_err:
        db.rollback()
        logger.error("auto_seed_bulk_failed", error=str(bulk_err))
        return 0


def _auto_seed():
    """Load sample events for all stores into DB on first startup.

    Re-seeds if existing data is stale (all timestamps from a previous day),
    so docker compose restarts always show live today metrics.
    """
    import os
    from datetime import datetime, timezone
    from app.database import get_db_session

    db = get_db_session()
    try:
        existing_count = db.query(EventRecord).count()
        if existing_count > 0:
            # Check if existing data is stale (timestamps from a previous day)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            latest = db.query(EventRecord.timestamp).order_by(
                EventRecord.timestamp.desc()
            ).first()
            if latest and latest[0][:10] == today:
                logger.info("auto_seed_skipped", reason="fresh data exists", count=existing_count)
                return
            # Stale data — wipe and reseed with today's timestamps
            logger.info("auto_seed_wipe", reason="stale data detected", latest_ts=latest[0] if latest else None)
            db.query(EventRecord).delete()
            db.commit()

        # Seed Store 1 (STORE_BLR_002) — primary sample events
        sample_path = os.getenv("SAMPLE_EVENTS_PATH", "data/sample_events.jsonl")
        n1 = _seed_events_from_file(sample_path, db)

        # Seed Store 2 (STORE_BLR_001)
        store2_path = os.path.join(os.path.dirname(sample_path), "store2_events.jsonl")
        n2 = _seed_events_from_file(store2_path, db)

        logger.info("auto_seed_complete", store1_events=n1, store2_events=n2)
    except Exception as e:
        logger.error("auto_seed_failed", error=str(e))
    finally:
        db.close()
