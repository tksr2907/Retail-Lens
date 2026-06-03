<div align="center">

<img src="https://img.shields.io/badge/Purplle_Tech_Challenge_2026-Store_Intelligence-7c3aed?style=for-the-badge&labelColor=0f0f1a" />

# RetailLens — Store Intelligence System

### *Raw CCTV Footage → YOLOv8n Detection → Real-Time Retail Analytics*

<br/>

[![Tests](https://img.shields.io/badge/Tests-91%20passing-22c55e?style=flat-square&logo=pytest&logoColor=white)](./tests)
[![Coverage](https://img.shields.io/badge/Coverage-79%25-22c55e?style=flat-square&logo=codecov&logoColor=white)](./tests)
[![Assertions](https://img.shields.io/badge/Assertions-10%2F10%20✓-22c55e?style=flat-square)](./assertions.py)
[![Docker](https://img.shields.io/badge/Docker-one--command%20start-2563eb?style=flat-square&logo=docker&logoColor=white)](./docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-15%20endpoints-009688?style=flat-square&logo=fastapi&logoColor=white)](http://localhost:8000/docs)
[![WebSocket](https://img.shields.io/badge/WebSocket-live%20push%203s-f59e0b?style=flat-square)](http://localhost:8000)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](./requirements.txt)

<br/>

> **Two stores. Four cameras each. 455 real detections. 15 API endpoints. One `docker compose up`.**

<br/>

</div>

---

## ⚡ Quick Start — 5 Commands

```bash
# 1. Clone
git clone <repo-url> && cd RetailLens

# 2. Start API + Live Dashboard (auto-seeds with today's data)
docker compose up --build

# 3. Open dashboard → http://localhost:8000

# 4. Run all 10 acceptance assertions
python assertions.py --api-url http://localhost:8000

# 5. Replay events in simulated real time (watch dashboard update live)
python -m pipeline.replay --file data/sample_events.jsonl \
  --api-url http://localhost:8000 --speed 10
```

| Service | URL |
|---|---|
| 🖥️ Live Dashboard | http://localhost:8000 |
| 📖 Swagger / OpenAPI | http://localhost:8000/docs |
| 📊 Acceptance Gate Metrics | http://localhost:8000/metrics |
| 💚 Health | http://localhost:8000/health |

> **No video files needed to see live data.** `docker compose up` automatically seeds `data/sample_events.jsonl` with timestamps shifted to today — all metrics are live the moment the container starts.

---

## What Was Built

This is a **complete end-to-end system** — from raw camera footage to queryable store analytics:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Raw CCTV Clips (1080p, 15fps, face-blurred)                          │
│   Store 1: CAM_3_entry · CAM_1_zone · CAM_2_zone · CAM_5_billing       │
│   Store 2: entry_1 · entry_2 · zone · billing_area                     │
│                           │                                             │
│                           ▼                                             │
│   ┌──────────────────────────────────────────────────────────┐         │
│   │  Detection Pipeline  (pipeline/)                         │         │
│   │                                                          │         │
│   │  YOLOv8n ──► ByteTracker ──► Re-ID ──► Zone Classifier  │         │
│   │  (person)   (IoU match)   (HSV hist) (store_layout.json) │         │
│   │                                                          │         │
│   │  Handles: group entry · staff exclusion · re-entry       │         │
│   │           partial occlusion · billing queue · empty store │         │
│   └──────────────────────────────────────────────────────────┘         │
│                           │                                             │
│              JSONL stream + HTTP POST batches                           │
│                           │                                             │
│                           ▼                                             │
│   ┌──────────────────────────────────────────────────────────┐         │
│   │  Intelligence API  (FastAPI + SQLite)                    │         │
│   │                                                          │         │
│   │  POST /events/ingest          (idempotent, batch 500)    │         │
│   │  GET  /stores/{id}/metrics    (visitors · conversion)    │         │
│   │  GET  /stores/{id}/funnel     (entry → billing → buy)    │         │
│   │  GET  /stores/{id}/heatmap    (zone frequency 0–100)     │         │
│   │  GET  /stores/{id}/anomalies  (5 types, 3 severities)    │         │
│   │  GET  /stores/{id}/revenue    (POS-correlated GMV)       │         │
│   │  GET  /stores/{id}/hourly     (24-hour traffic)          │         │
│   │  GET  /stores/{id}/journey    (zone-to-zone paths)       │         │
│   │  GET  /stores/{id}/summary    (all-in-one)               │         │
│   │  GET  /stores/compare         (multi-store ranking)      │         │
│   │  WS   /ws/stores/{id}         (live push every 3s)       │         │
│   │  + 4 more (pos · confidence · export · health)           │         │
│   └──────────────────────────────────────────────────────────┘         │
│                           │                                             │
│                           ▼                                             │
│   Live Dashboard (Chart.js + WebSocket)                                 │
│   Multi-store tabs · Zone heatmap · Funnel bars · Hourly traffic        │
│   Anomaly panel · Customer journey paths · Confidence stats             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Detection Pipeline — How It Works

### Stage 1: Person Detection

The pipeline uses **dual-mode detection** — automatically selects the best available method:

| Mode | When Used | Performance |
|---|---|---|
| **YOLOv8n** (primary) | `torch` + `ultralytics` installed | ~30ms/frame — runs above real-time |
| **OpenCV MOG2** (fallback) | CPU-only, no YOLO | 89fps at 320×180 — fast and robust |

Processing runs at **stride=3** (every 3rd frame → 5fps effective from 15fps input), balancing accuracy with throughput.

### Stage 2: Multi-Object Tracking (ByteTrack-style)

```
High-conf detections (≥0.5) → IoU match against active tracks
Low-conf  detections (<0.5)  → IoU match against remaining unmatched tracks
Unmatched detections         → Re-ID check → new visitor or REENTRY
```

Key behaviours:
- **Group entry**: Each bounding box = independent track = separate `ENTRY` event. Three people entering together → three `ENTRY` events.
- **Partial occlusion**: Low-confidence detections are *never* dropped — they follow the low-conf matching path and set `confidence` in the event. The `/confidence` endpoint shows distribution across five buckets.
- **Empty store**: Tracker emits zero events. All API endpoints return zero counts — never null, never 500.

### Stage 3: Re-Identification (Reentry Detection)

Faces are fully blurred — Re-ID runs on **torso appearance only**:

1. Extract 96-dim HSV colour histogram from the upper 60% of each detection crop
2. When a track is lost, store its histogram in a 30-second lookback pool
3. New detection → cosine similarity check against pool → if sim ≥ 0.75 → emit `REENTRY` event, preserve `visitor_id`

This prevents the re-entry inflation problem where one customer who steps out briefly is counted as two visitors.

### Stage 4: Staff Exclusion

Two-stage heuristic (no face recognition needed):
1. **Appearance**: Flat hue distribution in HSV histogram → uniform/monochrome clothing → `is_staff=True`
2. **Behaviour**: ≥4 distinct zones visited → typical staff movement pattern

All events from a staff track carry `is_staff=True` and are excluded from every customer metric.

### What the Pipeline Produced

Running on the actual CCTV footage:

| Store | Cameras Processed | Events Generated | Unique Visitors |
|---|---|---|---|
| **STORE_BLR_002** (Brigade Rd) | 4 | 132 | 18 |
| **STORE_BLR_001** (MG Road) | 4 | 323 | 91 |

Events include all 8 types: `ENTRY`, `EXIT`, `ZONE_ENTER`, `ZONE_EXIT`, `ZONE_DWELL`, `BILLING_QUEUE_JOIN`, `BILLING_QUEUE_ABANDON`, `REENTRY`.

---

## Running the Detection Pipeline

### Step 1 — Place your video files

```
data/
├── store1/
│   ├── CAM_3_entry.mp4        ← entry/exit tripwire
│   ├── CAM_1_zone.mp4         ← Skincare / Makeup / Fragrance zones
│   ├── CAM_2_zone.mp4         ← Haircare / Bath & Body / Accessories
│   └── CAM_5_billing.mp4      ← Cash counter
└── store2/
    ├── entry_1.mp4
    ├── entry_2.mp4
    ├── zone.mp4
    └── billing_area.mp4
```

### Step 2 — Run detection

```bash
# Both stores (uses YOLOv8n if available, MOG2 fallback)
python -m pipeline.detect_real --store both

# Single store
python -m pipeline.detect_real --store STORE_BLR_002

# Quick test — first 30s per clip only
python -m pipeline.detect_real --store both --max-frames 450

# With real-time push to running API
python -m pipeline.detect_real --store both --api-url http://localhost:8000
```

### Step 3 — Via Docker (pipeline profile)

```bash
# Full detection on all clips
docker compose --profile pipeline up

# First 30s per clip (~2 min total on CPU)
MAX_FRAMES=450 docker compose --profile pipeline up
```

The pipeline service waits for the API to pass its health check before starting, then writes events to `data/events_yolo.jsonl` and simultaneously POSTs to `/events/ingest`.

### Step 4 — Simulated real-time replay

```bash
# Replay pre-generated events at 10× speed — live dashboard updates visible
python -m pipeline.replay \
  --file data/sample_events.jsonl \
  --api-url http://localhost:8000 \
  --speed 10

# 1× speed (real time)
python -m pipeline.replay --file data/sample_events.jsonl --speed 1
```

---

## API Reference

### Core Endpoints

#### `POST /events/ingest`
Accepts batches of up to 500 events. Idempotent by `event_id` — safe to call twice.

```bash
curl -X POST http://localhost:8000/events/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "events": [{
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "store_id": "STORE_BLR_002",
      "camera_id": "CAM_ENTRY_01",
      "visitor_id": "VIS_c8a2f1",
      "event_type": "ENTRY",
      "timestamp": "2026-04-10T14:22:10Z",
      "zone_id": null,
      "dwell_ms": 0,
      "is_staff": false,
      "confidence": 0.91,
      "metadata": {"queue_depth": null, "sku_zone": null, "session_seq": 1}
    }]
  }'
```

Response:
```json
{"accepted": 1, "duplicate": 0, "rejected": 0, "errors": []}
```

#### `GET /stores/{id}/metrics`

```json
{
  "store_id": "STORE_BLR_002",
  "unique_visitors": 18,
  "conversion_rate": 0.3333,
  "avg_dwell_ms": 142800,
  "queue_depth": 0,
  "abandonment_rate": 0.0,
  "as_of": "2026-06-03T12:00:00Z"
}
```

#### `GET /stores/{id}/funnel`

```json
{
  "store_id": "STORE_BLR_002",
  "stages": [
    {"stage": "Entry",        "count": 18, "drop_off_pct": 0.0},
    {"stage": "Zone Visit",   "count": 15, "drop_off_pct": 16.7},
    {"stage": "Billing Zone", "count": 8,  "drop_off_pct": 46.7},
    {"stage": "Purchase",     "count": 6,  "drop_off_pct": 25.0}
  ]
}
```

Sessions are the unit — re-entries do not double-count a visitor.

#### `GET /stores/{id}/anomalies`

```json
{
  "anomalies": [
    {
      "anomaly_type": "CONVERSION_DROP",
      "severity": "WARN",
      "message": "Conversion rate 12% vs 7-day avg 28% — 57% drop",
      "suggested_action": "Check billing staff availability and queue depth"
    }
  ]
}
```

Five anomaly types: `BILLING_QUEUE_SPIKE` · `CONVERSION_DROP` · `DEAD_ZONE` · `STALE_CAMERA_FEED` · `HIGH_ABANDONMENT_RATE`

Three severity levels: `INFO` · `WARN` · `CRITICAL`

#### `GET /stores/{id}/heatmap`

```json
{
  "zones": [
    {"zone_id": "SKINCARE",   "visit_count": 12, "avg_dwell_ms": 95000, "score": 100},
    {"zone_id": "MAKEUP",     "visit_count": 9,  "avg_dwell_ms": 72000, "score": 75},
    {"zone_id": "FRAGRANCE",  "visit_count": 3,  "avg_dwell_ms": 28000, "score": 25}
  ],
  "data_confidence": "HIGH"
}
```

Scores normalised 0–100. `data_confidence: "LOW"` flag if fewer than 20 sessions in window.

#### `GET /health`

```json
{
  "status": "OK",
  "stores": {
    "STORE_BLR_002": {"last_event": "2026-06-03T11:58:10Z", "feed_status": "OK"},
    "STORE_BLR_001": {"last_event": "2026-06-03T11:57:44Z", "feed_status": "OK"}
  }
}
```

`feed_status: "STALE_FEED"` if last event > 10 minutes ago.

### All Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/events/ingest` | Batch ingest, idempotent by event_id |
| `GET` | `/metrics` | Acceptance gate — KPI summary all stores |
| `GET` | `/stores/{id}/metrics` | Unique visitors, conversion rate, dwell |
| `GET` | `/stores/{id}/funnel` | Entry → Zone → Billing → Purchase |
| `GET` | `/stores/{id}/heatmap` | Zone frequency + dwell, 0–100 |
| `GET` | `/stores/{id}/anomalies` | 5 anomaly types, 3 severities |
| `GET` | `/stores/{id}/revenue` | POS-correlated GMV, basket value |
| `GET` | `/stores/{id}/hourly` | 24-hour traffic, peak hour |
| `GET` | `/stores/{id}/journey` | Zone-to-zone customer paths |
| `GET` | `/stores/{id}/summary` | All metrics in one call |
| `GET` | `/stores/{id}/pos` | Department / brand / SKU breakdown |
| `GET` | `/stores/{id}/confidence` | Detection confidence distribution |
| `GET` | `/stores/{id}/export` | Full event export (JSON or CSV) |
| `GET` | `/stores/compare` | Multi-store ranking by conversion |
| `WS` | `/ws/stores/{id}` | Live push every 3 seconds |
| `GET` | `/health` | Service status + STALE_FEED per store |

---

## Event Schema

```json
{
  "event_id":   "uuid-v4",
  "store_id":   "STORE_BLR_002",
  "camera_id":  "CAM_ENTRY_01",
  "visitor_id": "VIS_c8a2f1",
  "event_type": "ZONE_DWELL",
  "timestamp":  "2026-04-10T14:22:10Z",
  "zone_id":    "SKINCARE",
  "dwell_ms":   8400,
  "is_staff":   false,
  "confidence": 0.91,
  "metadata": {
    "queue_depth": null,
    "sku_zone":    "MOISTURISER",
    "session_seq": 5
  }
}
```

| Event Type | When Emitted |
|---|---|
| `ENTRY` | Visitor crosses entry threshold inbound — new session |
| `EXIT` | Visitor crosses entry threshold outbound — closes session |
| `ZONE_ENTER` | Visitor enters a named zone |
| `ZONE_EXIT` | Visitor leaves a named zone |
| `ZONE_DWELL` | Visitor in zone continuously for 30+ seconds (emitted every 30s) |
| `BILLING_QUEUE_JOIN` | Visitor enters billing zone while queue_depth > 0 |
| `BILLING_QUEUE_ABANDON` | Visitor leaves billing before a POS transaction follows |
| `REENTRY` | Same visitor_id detected after a prior EXIT |

---

## Production Design Decisions

### Why SQLite — and the upgrade path

SQLite gives zero-ops simplicity for the evaluation scenario — the entire database is one file, `docker compose up` just works. The critical design choice was exposing `DATABASE_URL` as an environment variable so swapping to PostgreSQL requires **zero code changes**:

```bash
DATABASE_URL=postgresql://user:pass@host/db docker compose up
```

Three composite indexes cover all hot-path queries: `(store_id, event_type)`, `(store_id, visitor_id)`, `(store_id, timestamp)`.

### Idempotency

`event_id` has a database-level `UNIQUE` constraint. A second ingest of the same event catches `IntegrityError`, increments the `duplicate` counter, and continues processing the rest of the batch. This makes `/events/ingest` safe to call repeatedly without data corruption — verified in tests.

### Conversion Signal: Camera + POS (dual)

- **Camera-based** (real-time): `ZONE_ENTER(BILLING)` minus `BILLING_QUEUE_ABANDON`. Available immediately.
- **POS-based** (confirmed): 5-minute time-window correlation between billing zone presence and a POS transaction. Exposed via `/revenue`. More accurate, slightly lagged.

Both signals are surfaced. `/metrics` uses the camera signal for real-time accuracy; `/revenue` uses POS for confirmed GMV.

### Graceful Degradation

- Database unavailable → `HTTP 503` with structured JSON body, no stack trace in response
- Zero-traffic store → all endpoints return zeroes, not nulls or 500s
- YOLO unavailable → automatic fallback to OpenCV MOG2 detection
- Missing video file → skip and continue with a warning log

### Auto-Seed with Time Shift

On startup, `sample_events.jsonl` timestamps are shifted so the *latest* event lands 2 minutes ago. This ensures `/health` always shows `OK` (not `STALE_FEED`) and all metric windows are populated regardless of when the container is started.

---

## Tests

```bash
# No Docker required — uses in-memory SQLite
pip install fastapi uvicorn pydantic sqlalchemy structlog \
            python-multipart httpx pytest pytest-cov numpy

pytest --tb=short                           # 91 tests, all passing
pytest --cov=app --cov-report=term-missing  # 79% statement coverage
python assertions.py --api-url http://localhost:8000  # 10/10 assertions
```

Test files include AI prompt blocks at the top (`# PROMPT: ...` / `# CHANGES MADE: ...`) per challenge specification.

Edge cases covered: empty store, all-staff clip, zero purchases, re-entry in funnel, idempotent double-ingest, `STORE_EMPTY` fixture, `STALE_FEED` detection.

---

## Edge Cases Handled

| Edge Case | Implementation |
|---|---|
| **Group entry** | ByteTracker assigns independent track IDs to simultaneous detections via IoU matching. Three people entering together → three separate `ENTRY` events. |
| **Staff movement** | Two-stage: flat HSV hue histogram (uniform/monochrome clothing) + ≥4 distinct zones visited. `is_staff=True` on all events from that track. |
| **Re-entry** | Lost tracks held in a 30-second lookback pool. New detection checked via cosine similarity against pool. Match → `REENTRY` event, same `visitor_id` preserved. |
| **Partial occlusion** | Low-confidence detections are never dropped. They follow ByteTrack's low-conf matching path and their `confidence` value is preserved in the event. |
| **Billing queue buildup** | `queue_depth` = count of active billing visitors at moment of join. `BILLING_QUEUE_ABANDON` emitted when a visitor leaves the billing zone without a POS match within 5 minutes. |
| **Empty store periods** | Zero-event windows return zero counts. Explicitly tested with the `STORE_EMPTY` fixture — no nulls, no crashes. |
| **Camera angle overlap** | Entry cameras emit only `ENTRY`/`EXIT`. Floor cameras emit only zone events. Same physical space → different event types → no double-counting. |

---

## Project Structure

```
RetailLens/
├── pipeline/
│   ├── detect.py        # YOLOv8n + ByteTracker + zone classifier
│   ├── detect_real.py   # Entry point for real-clip processing (both stores)
│   ├── tracker.py       # Re-ID tracking (HSV histogram cosine similarity)
│   ├── emit.py          # Event schema + JSONL emission
│   ├── replay.py        # Simulated real-time replay into API
│   └── run.sh           # One-command pipeline execution
├── app/
│   ├── main.py          # FastAPI entrypoint (15 endpoints + WebSocket)
│   ├── models.py        # Pydantic event schema + response models
│   ├── ingestion.py     # Ingest, dedup, partial success
│   ├── metrics.py       # Real-time metric computation
│   ├── funnel.py        # Session-based funnel + deduplication
│   ├── heatmap.py       # Zone heatmap 0–100 normalisation
│   ├── anomalies.py     # 5 anomaly types with severity + suggested_action
│   ├── health.py        # Health + STALE_FEED detection
│   ├── revenue.py       # POS correlation + basket analytics
│   ├── hourly.py        # 24-hour traffic bucketing
│   ├── journey.py       # Zone-to-zone path analysis
│   ├── pos.py           # POS CSV loading + correlation
│   ├── dashboard.py     # Live HTML dashboard (Chart.js + WebSocket)
│   ├── logger.py        # Structured logging middleware
│   └── database.py      # SQLAlchemy + EventRecord schema
├── tests/
│   ├── conftest.py      # Fixtures: in-memory DB, test client, seed helpers
│   ├── test_pipeline.py # Pipeline unit tests — schema, tracker, emitter
│   ├── test_metrics.py  # API tests — ingest, metrics, funnel, heatmap
│   ├── test_anomalies.py# Anomaly detection tests
│   └── test_extended.py # Hourly, journey, revenue, health, export, compare
├── docs/
│   ├── DESIGN.md        # Architecture + AI-Assisted Decisions (3 documented)
│   └── CHOICES.md       # 3 key decisions with full reasoning
├── data/
│   ├── store_layout.json      # Zone definitions + camera map for STORE_BLR_002
│   ├── store2_layout.json     # Zone definitions for STORE_BLR_001
│   ├── sample_events.jsonl    # 455 real detected events (auto-seeded on startup)
│   ├── store2_events.jsonl    # STORE_BLR_001 events
│   └── pos_transactions.csv   # POS transactions for correlation
├── docker-compose.yml         # API service + optional pipeline profile
├── Dockerfile                 # Python 3.11-slim, CPU-only PyTorch
├── assertions.py              # 10 integration assertions (all pass)
├── requirements.txt
└── README.md
```

---

## North Star Metric

> **Offline Store Conversion Rate** = Visitors who completed a purchase ÷ Total unique visitors

Every pipeline stage either improves the accuracy of this number (detection layer) or makes it actionable (API layer):

| Business Question | Where the System Answers It |
|---|---|
| How many customers visited and bought today? | Detection accuracy + `/metrics` conversion_rate |
| Where in the store are we losing customers? | `/funnel` drop-off % by stage |
| Which zones get attention but not sales? | `/heatmap` dwell vs `/funnel` billing stage |
| Is there a queue building right now? | `/anomalies` BILLING_QUEUE_SPIKE |
| Is today's conversion worse than usual? | `/anomalies` CONVERSION_DROP (7-day baseline) |
| Is any camera or store feed stale? | `/health` STALE_FEED warning |

---

## Docs

- [`docs/DESIGN.md`](./docs/DESIGN.md) — Full architecture + **AI-Assisted Decisions** section: 3 documented cases where an LLM shaped the design, with explicit agreement/override rationale
- [`docs/CHOICES.md`](./docs/CHOICES.md) — Three key decisions: detection model selection, event schema design, API architecture choice — each with options considered, AI suggestions, and final reasoning

---

<div align="center">

Built for the **Purplle Tech Challenge 2026** · Apex Retail Store Intelligence

*Detection → Events → Analytics → Decisions*

</div>
