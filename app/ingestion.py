"""
Event ingestion: validate, deduplicate, store.

Key requirements:
- Idempotent by event_id (duplicate ingests are safe)
- Partial success on malformed events (don't reject whole batch)
- Structured error responses
"""

from typing import List, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models import StoreEvent, IngestResponse
from app.database import EventRecord


def ingest_events(
    events: List[StoreEvent], db: Session
) -> IngestResponse:
    accepted = 0
    rejected = 0
    duplicate = 0
    errors = []

    for ev in events:
        try:
            record = EventRecord(
                event_id=ev.event_id,
                store_id=ev.store_id,
                camera_id=ev.camera_id,
                visitor_id=ev.visitor_id,
                event_type=ev.event_type,
                timestamp=ev.timestamp,
                zone_id=ev.zone_id,
                dwell_ms=ev.dwell_ms,
                is_staff=ev.is_staff,
                confidence=ev.confidence,
                queue_depth=ev.metadata.queue_depth,
                sku_zone=ev.metadata.sku_zone,
                session_seq=ev.metadata.session_seq,
                ingested_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
            db.add(record)
            db.commit()
            accepted += 1
        except IntegrityError:
            db.rollback()
            duplicate += 1
        except Exception as e:
            db.rollback()
            rejected += 1
            errors.append({
                "event_id": getattr(ev, "event_id", "unknown"),
                "error": str(e),
            })

    return IngestResponse(
        accepted=accepted,
        rejected=rejected,
        duplicate=duplicate,
        errors=errors,
    )
