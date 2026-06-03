<div align="center">

<img src="https://img.shields.io/badge/Purplle_Tech_Challenge_2026-Store_Intelligence-7c3aed?style=for-the-badge&labelColor=0f0f1a" />

<br/><br/>

# 🏪 RetailLens — Store Intelligence System

### *Raw CCTV Footage → YOLOv8n Detection → Real-Time Retail Analytics*

<br/>

[![Live Demo](https://img.shields.io/badge/🚀_Live_Demo-retail--lens--production--9acd.up.railway.app-7c3aed?style=for-the-badge)](https://retail-lens-production-9acd.up.railway.app)

<br/>

[![Tests](https://img.shields.io/badge/Tests-91%20passing-22c55e?style=flat-square&logo=pytest&logoColor=white)](./tests)
[![Coverage](https://img.shields.io/badge/Coverage-79%25-22c55e?style=flat-square&logo=codecov&logoColor=white)](./tests)
[![Assertions](https://img.shields.io/badge/Assertions-10%2F10%20✓-22c55e?style=flat-square)](./assertions.py)
[![Docker](https://img.shields.io/badge/Docker-one--command%20start-2563eb?style=flat-square&logo=docker&logoColor=white)](./docker-compose.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-15%20endpoints-009688?style=flat-square&logo=fastapi&logoColor=white)](https://retail-lens-production-9acd.up.railway.app/docs)
[![WebSocket](https://img.shields.io/badge/WebSocket-live%20push%203s-f59e0b?style=flat-square)](https://retail-lens-production-9acd.up.railway.app)
[![Railway](https://img.shields.io/badge/Deployed-Railway-0B0D0E?style=flat-square&logo=railway&logoColor=white)](https://retail-lens-production-9acd.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab?style=flat-square&logo=python&logoColor=white)](./requirements.txt)

<br/>

> **Two stores. Four cameras each. 455 real detections. 15 API endpoints. One `docker compose up`.**

<br/>

| 🖥️ Live Dashboard | 📖 API Docs | 📊 Metrics | 💚 Health |
|:---:|:---:|:---:|:---:|
| [Open Dashboard](https://retail-lens-production-9acd.up.railway.app) | [Swagger UI](https://retail-lens-production-9acd.up.railway.app/docs) | [/metrics](https://retail-lens-production-9acd.up.railway.app/metrics) | [/health](https://retail-lens-production-9acd.up.railway.app/health) |

<br/>

</div>

---

## ⚡ Quick Start — 5 Commands

```bash
# 1. Clone
git clone https://github.com/tksr2907/Retail-Lens.git && cd Retail-Lens

# 2. Start API + Live Dashboard (auto-seeds with today's data)
docker compose up --build

# 3. Open dashboard → http://localhost:8000

# 4. Run all 10 acceptance assertions
python assertions.py --api-url http://localhost:8000

# 5. Replay events in simulated real time (watch dashboard update live)
python -m pipeline.replay --file data/sample_events.jsonl \
  --api-url http://localhost:8000 --speed 10
```

> **No video files needed to see live data.** `docker compose up` automatically seeds `data/sample_events.jsonl` with timestamps shifted to today — all metrics are live the moment the container starts.

> **Or skip local setup entirely** — the system is already live at [retail-lens-production-9acd.up.railway.app](https://retail-lens-production-9acd.up.railway.app)

---

## 🧠 What Was Built

A **complete end-to-end offline store analytics system** — the same problem every major retailer hasn't solved yet:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   Raw CCTV Clips  (1080p · 15fps · face-blurred · 2 stores)            │
│   Store 1: CAM_3_entry · CAM_1_zone · CAM_2_zone · CAM_5_billing       │
│   Store 2: entry_1 · entry_2 · zone · billing_area                     │
│                           │                                             │
│                           ▼                                             │
│   ┌──────────────────────────────────────────────────────────┐         │
│   │            Detection Pipeline  (pipeline/)               │         │
│   │                                                          │         │
│   │   YOLOv8n ──► ByteTracker ──► Re-ID ──► Zone Classifier │         │
│   │   (person)   (IoU match)   (HSV hist) (store_layout.json)│         │
│   │                                                          │         │
│   │   ✓ Group entry    ✓ Staff exclusion   ✓ Re-entry        │         │
│   │   ✓ Partial occl.  ✓ Billing queue    ✓ Empty store      │         │
│   └──────────────────────────────────────────────────────────┘         │
│                           │                                             │
│              JSONL stream + HTTP POST batches                           │
│                           │                                             │
│                           ▼                                             │
│   ┌──────────────────────────────────────────────────────────┐         │
│   │          Intelligence API  (FastAPI + SQLite)            │         │
│   │                                                          │         │
│   │  POST /events/ingest      ← idempotent · batch 500       │         │
│   │  GET  /stores/{id}/metrics    visitors · conversion      │         │
│   │  GET  /stores/{id}/funnel     entry → billing → buy      │         │
│   │  GET  /stores/{id}/heatmap    zone frequency 0–100       │         │
│   │  GET  /stores/{id}/anomalies  5 types · 3 severities     │         │
│   │  GET  /stores/{id}/revenue    POS-correlated GMV         │         │
│   │  GET  /stores/{id}/hourly     24-hour traffic            │         │
│   │  GET  /stores/{id}/journey    zone-to-zone paths         │         │
│   │  GET  /stores/{id}/summary    all-in-one                 │         │
│   │  GET  /stores/compare         multi-store ranking        │         │
│   │  WS   /ws/stores/{id}         live push every 3s         │         │
│   │  + pos · confidence · export · health                    │         │
│   └──────────────────────────────────────────────────────────┘         │
│                           │                                             │
│                           ▼                                             │
│        Live Dashboard (Chart.js + WebSocket · no page refresh)         │
│   Zone heatmap · Funnel bars · Hourly traffic · Anomaly panel          │
│   Customer journey paths · Confidence stats · Multi-store tabs         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 North Star Metric

<div align="center">

### Offline Store Conversion Rate
#### `Visitors who completed a purchase ÷ Total unique visitors`

</div>

Every pipeline stage either improves the **accuracy** of this number (detection layer) or makes it **actionable** (API layer):

| Business Question | Where the System Answers It |
|---|---|
| How many customers visited and bought today? | Detection accuracy + [`/metrics`](https://retail-lens-production-9acd.up.railway.app/stores/STORE_BLR_002/metrics) `conversion_rate` |
| Where in the store are we losing customers? | [`/funnel`](https://retail-lens-production-9acd.up.railway.app/stores/STORE_BLR_002/funnel) drop-off % by stage |
| Which zones get attention but not sales? | [`/heatmap`](https://retail-lens-production-9acd.up.railway.app/stores/STORE_BLR_002/heatmap) dwell vs funnel billing stage |
| Is there a queue building right now? | [`/anomalies`](https://retail-lens-production-9acd.up.railway.app/stores/STORE_BLR_002/anomalies) `BILLING_QUEUE_SPIKE` |
| Is today's conversion worse than usual? | `/anomalies` `CONVERSION_DROP` (7-day baseline) |
| Is any camera or store feed stale? | [`/health`](https://retail-lens-production-9acd.up.railway.app/health) `STALE_FEED` warning |

---

## 🔬 Detection Pipeline — How It Works

### Stage 1 · Person Detection

Dual-mode — automatically picks the best available method:

| Mode | Condition | Speed |
|---|---|---|
| **YOLOv8n** (primary) | `torch` + `ultralytics` available | ~30ms/frame — above real-time |
| **OpenCV MOG2** (fallback) | CPU-only, no YOLO | 89fps at 320×180 |

Runs at **stride=3** → 5fps effective from 15fps input. Every 3rd frame is processed, giving ample headroom for real-time operation while reducing compute cost by 67%.

### Stage 2 · Multi-Object Tracking (ByteTrack-style)

```
High-conf detections (≥0.5)  →  IoU match against active tracks
Low-conf  detections (<0.5)  →  IoU match against remaining tracks
Unmatched detections         →  Re-ID check → new visitor or REENTRY
```

- **Group entry**: Each bounding box → independent track → separate `ENTRY` event. Three people entering together → three `ENTRY` events, not one.
- **Partial occlusion**: Low-confidence detections are **never dropped**. They follow the low-conf matching path with `confidence` preserved in the event. The `/confidence` endpoint exposes the full distribution.
- **Empty store**: Zero events → zero counts. Never null, never 500.

### Stage 3 · Re-Identification (Reentry Detection)

Faces are fully blurred — Re-ID runs on **torso appearance only**:

```
Detection crop → upper 60% (torso) → 96-dim HSV histogram
Lost track pool (30s window) → cosine similarity check
similarity ≥ 0.75 → REENTRY event, same visitor_id preserved
```

Solves the re-entry inflation problem: a customer who steps outside and returns is counted as **one visitor**, not two.

### Stage 4 · Staff Exclusion

No face recognition needed — pure heuristic:
1. **Appearance**: Flat hue distribution in HSV histogram → uniform/monochrome clothing
2. **Behaviour**: ≥4 distinct zones visited → staff movement pattern

All events from a staff track carry `is_staff=True` and are excluded from every customer metric at the database query level.

### Detection Results

| Store | Cameras | Events | Unique Visitors |
|---|---|---|---|
| **STORE_BLR_002** — Brigade Rd | 4 | 132 | 18 |
| **STORE_BLR_001** — MG Road | 4 | 323 | 91 |

---

## 🚀 Running the Detection Pipeline

### With your own video clips

```bash
# Place clips in data/store1/ and data/store2/
# then run:

# Both stores — auto-selects YOLOv8n or MOG2 fallback
python -m pipeline.detect_real --store both

# Quick test — first 30 seconds per clip only
python -m pipeline.detect_real --store both --max-frames 450

# With live push to running API
python -m pipeline.detect_real --store both --api-url http://localhost:8000
```

### Via Docker

```bash
# Full detection
docker compose --profile pipeline up

# Quick demo (~2 min on CPU)
MAX_FRAMES=450 docker compose --profile pipeline up
```

### Simulated real-time replay

```bash
python -m pipeline.replay \
  --file data/sample_events.jsonl \
  --api-url http://localhost:8000 \
  --speed 10   # 10× faster than real time
```

---

## 📡 API Reference

### `POST /events/ingest`

Idempotent batch ingest — safe to call twice with the same payload.

```bash
curl -X POST https://retail-lens-production-9acd.up.railway.app/events/ingest \
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

```json
{"accepted": 1, "duplicate": 0, "rejected": 0, "errors": []}
```

### `GET /stores/{id}/metrics`

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

### `GET /stores/{id}/funnel`

```json
{
  "stages": [
    {"stage": "Entry",        "count": 18, "drop_off_pct": 0.0},
    {"stage": "Zone Visit",   "count": 15, "drop_off_pct": 16.7},
    {"stage": "Billing Zone", "count": 8,  "drop_off_pct": 46.7},
    {"stage": "Purchase",     "count": 6,  "drop_off_pct": 25.0}
  ]
}
```

### `GET /stores/{id}/anomalies`

```json
{
  "anomalies": [{
    "anomaly_type": "CONVERSION_DROP",
    "severity": "WARN",
    "message": "Conversion 12% vs 7-day avg 28% — 57% drop",
    "suggested_action": "Check billing staff availability and queue depth"
  }]
}
```

**5 anomaly types:** `BILLING_QUEUE_SPIKE` · `CONVERSION_DROP` · `DEAD_ZONE` · `STALE_CAMERA_FEED` · `HIGH_ABANDONMENT_RATE`

**3 severity levels:** `INFO` · `WARN` · `CRITICAL`

### All 15 Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/events/ingest` | Batch ingest · idempotent by event_id |
| `GET` | `/metrics` | Acceptance gate · all-store KPI summary |
| `GET` | `/stores/{id}/metrics` | Visitors · conversion · dwell · queue |
| `GET` | `/stores/{id}/funnel` | Entry → Zone → Billing → Purchase |
| `GET` | `/stores/{id}/heatmap` | Zone frequency + dwell · normalised 0–100 |
| `GET` | `/stores/{id}/anomalies` | 5 anomaly types · 3 severities |
| `GET` | `/stores/{id}/revenue` | POS-correlated GMV · basket value |
| `GET` | `/stores/{id}/hourly` | 24-hour traffic · peak hour |
| `GET` | `/stores/{id}/journey` | Zone-to-zone customer paths |
| `GET` | `/stores/{id}/summary` | All metrics in one call |
| `GET` | `/stores/{id}/pos` | Department · brand · SKU breakdown |
| `GET` | `/stores/{id}/confidence` | Detection confidence distribution |
| `GET` | `/stores/{id}/export` | Full event export (JSON or CSV) |
| `GET` | `/stores/compare` | Multi-store ranking by conversion |
| `WS` | `/ws/stores/{id}` | Live push every 3 seconds |
| `GET` | `/health` | Service status · STALE_FEED per store |

---

## 📋 Event Schema

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
| `ENTRY` | Visitor crosses entry threshold inbound — opens session |
| `EXIT` | Visitor crosses entry threshold outbound — closes session |
| `ZONE_ENTER` | Visitor enters a named zone |
| `ZONE_EXIT` | Visitor leaves a named zone |
| `ZONE_DWELL` | Visitor in zone for 30+ seconds (emitted every 30s) |
| `BILLING_QUEUE_JOIN` | Visitor enters billing while queue_depth > 0 |
| `BILLING_QUEUE_ABANDON` | Visitor leaves billing before a POS transaction follows |
| `REENTRY` | Same visitor_id detected after a prior EXIT |

---

## 🛡️ Edge Cases Handled

| Edge Case | How |
|---|---|
| **Group entry** | ByteTracker assigns independent track IDs via IoU. 3 people → 3 `ENTRY` events. |
| **Staff movement** | Flat HSV hue histogram (uniform) + ≥4 distinct zones visited → `is_staff=True` on all events. |
| **Re-entry** | 30s lost-track pool + cosine similarity check → `REENTRY` event, same `visitor_id` preserved. |
| **Partial occlusion** | Low-confidence detections follow ByteTrack low-conf path — never dropped, `confidence` preserved. |
| **Billing queue buildup** | `queue_depth` = active billing visitors at join time. `BILLING_QUEUE_ABANDON` on exit without POS match. |
| **Empty store periods** | Zero events → zero counts. Tested with `STORE_EMPTY` fixture. Never null, never 500. |
| **Camera angle overlap** | Entry cameras emit `ENTRY`/`EXIT` only. Floor cameras emit zone events only. No double-counting. |

---

## 🏗️ Production Decisions

### SQLite with zero-code upgrade path
SQLite for zero-ops take-home simplicity. `DATABASE_URL` env var means PostgreSQL swap requires no code change:
```bash
DATABASE_URL=postgresql://user:pass@host/db docker compose up
```
Three composite indexes cover all hot-path queries: `(store_id, event_type)`, `(store_id, visitor_id)`, `(store_id, timestamp)`.

### Idempotency at the database level
`event_id` has a `UNIQUE` constraint. Double-ingest catches `IntegrityError`, increments `duplicate` counter, continues — never rejects the rest of the batch.

### Dual conversion signal
- **Camera** (real-time): `ZONE_ENTER(BILLING)` minus `BILLING_QUEUE_ABANDON`
- **POS** (confirmed): 5-minute time-window correlation with transaction timestamp

### Graceful degradation
- DB unavailable → `HTTP 503` structured JSON, no stack trace
- Zero-traffic store → zero counts, never null
- YOLO unavailable → OpenCV MOG2 fallback
- Missing video → skip + warn, continue

---

## 🧪 Tests

```bash
# No Docker, no video files needed
pip install fastapi uvicorn pydantic sqlalchemy structlog \
            python-multipart httpx pytest pytest-cov numpy

pytest --tb=short                            # 91 tests, all passing
pytest --cov=app --cov-report=term-missing   # 79% coverage
python assertions.py --api-url http://localhost:8000  # 10/10 ✓
```

Edge cases tested: empty store · all-staff clip · zero purchases · re-entry in funnel · idempotent double-ingest · `STALE_FEED` detection.

---

## 📁 Project Structure

```
RetailLens/
├── pipeline/
│   ├── detect.py          # YOLOv8n + ByteTracker + zone classifier
│   ├── detect_real.py     # Entry point for real-clip processing
│   ├── tracker.py         # Re-ID (HSV histogram cosine similarity)
│   ├── emit.py            # Event schema + JSONL emission
│   ├── replay.py          # Simulated real-time replay into API
│   └── run.sh             # One-command pipeline execution
├── app/
│   ├── main.py            # FastAPI · 15 endpoints + WebSocket
│   ├── models.py          # Pydantic event schema + responses
│   ├── ingestion.py       # Ingest · dedup · partial success
│   ├── metrics.py         # Real-time metric computation
│   ├── funnel.py          # Session-based funnel + deduplication
│   ├── heatmap.py         # Zone heatmap 0–100 normalisation
│   ├── anomalies.py       # 5 anomaly types · severity · suggested_action
│   ├── health.py          # Health + STALE_FEED detection
│   ├── revenue.py         # POS correlation + basket analytics
│   ├── hourly.py          # 24-hour traffic bucketing
│   ├── journey.py         # Zone-to-zone path analysis
│   ├── pos.py             # POS CSV loading + correlation
│   ├── dashboard.py       # Live HTML dashboard (Chart.js + WebSocket)
│   ├── logger.py          # Structured logging middleware
│   └── database.py        # SQLAlchemy + EventRecord schema
├── tests/
│   ├── conftest.py        # Fixtures: in-memory DB, test client
│   ├── test_pipeline.py   # Schema · tracker · emitter
│   ├── test_metrics.py    # Ingest · metrics · funnel · heatmap
│   ├── test_anomalies.py  # Anomaly detection
│   └── test_extended.py   # Hourly · journey · revenue · health · export
├── docs/
│   ├── DESIGN.md          # Architecture + AI-Assisted Decisions
│   └── CHOICES.md         # 3 decisions with full reasoning
├── data/
│   ├── store_layout.json       # STORE_BLR_002 zone + camera map
│   ├── store2_layout.json      # STORE_BLR_001 zone + camera map
│   ├── sample_events.jsonl     # 455 real detected events
│   ├── store2_events.jsonl     # STORE_BLR_001 events
│   └── pos_transactions.csv    # POS data for correlation
├── docker-compose.yml          # API + optional pipeline profile
├── Dockerfile                  # Python 3.11-slim · CPU-only PyTorch
├── assertions.py               # 10 integration assertions
└── requirements.txt
```

---

## 📚 Docs

- [`docs/DESIGN.md`](./docs/DESIGN.md) — Full architecture + **AI-Assisted Decisions** (3 cases: where AI was followed, partially overridden, and disagreed with — all documented with reasoning)
- [`docs/CHOICES.md`](./docs/CHOICES.md) — Three key decisions: detection model, event schema design, API architecture — each with options considered, AI suggestions, and final choice

---

<div align="center">

<br/>

**Built for the Purplle Tech Challenge 2026**

[![Live Demo](https://img.shields.io/badge/🚀_Try_It_Live-retail--lens--production--9acd.up.railway.app-7c3aed?style=for-the-badge)](https://retail-lens-production-9acd.up.railway.app)

<br/>

*Detection → Events → Analytics → Decisions*

*Raw CCTV → Offline Store Conversion Rate — solved end to end.*

</div>
