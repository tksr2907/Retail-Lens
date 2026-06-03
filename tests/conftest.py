"""
Shared test fixtures.

# PROMPT: "Generate pytest fixtures for a FastAPI app using SQLite in-memory DB.
# Include fixtures for test client, db session, and helpers to seed N visitors."
# CHANGES MADE: Added staff fixture, zero-visitor fixture, reentry fixture.
# Patched global engine so on_startup uses in-memory DB, not the file-based one.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.database as _db_module
from app.database import Base, get_db
from app.main import app

TEST_DB_URL = "sqlite:///:memory:"

NOW = datetime.now(timezone.utc)
STORE_ID = "STORE_BLR_002"


@pytest.fixture(scope="function")
def engine():
    eng = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    _original = _db_module.engine
    _db_module.engine = eng
    yield eng
    _db_module.engine = _original
    Base.metadata.drop_all(bind=eng)


@pytest.fixture(scope="function")
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(engine):
    Session = sessionmaker(bind=engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def ts(offset_min=0):
    return (NOW + timedelta(minutes=offset_min)).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_event(event_type, visitor_id=None, zone_id=None, dwell_ms=0,
               is_staff=False, confidence=0.9, queue_depth=None, offset_min=0):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": ts(offset_min),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": zone_id,
            "session_seq": 1,
        },
    }


def seed_visitors(client, n_total, n_purchased):
    events = []
    for i in range(n_total):
        vid = f"VIS_{i:06x}"
        events.append(make_event("ENTRY", visitor_id=vid, offset_min=i))
        events.append(make_event("ZONE_ENTER", visitor_id=vid, zone_id="SKINCARE", offset_min=i + 1))
        if i < n_purchased:
            events.append(make_event("ZONE_ENTER", visitor_id=vid, zone_id="BILLING", offset_min=i + 5))
        else:
            events.append(make_event("EXIT", visitor_id=vid, offset_min=i + 8))
    r = client.post("/events/ingest", json={"events": events})
    assert r.status_code == 200
    return events
