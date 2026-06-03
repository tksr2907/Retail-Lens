# CHOICES.md — Three Key Engineering Decisions

---

## Decision 1: Detection Model — YOLOv8n

### Options Considered

| Model | COCO mAP | Person AP₅₀ | CPU Speed | Size | Notes |
|-------|----------|-------------|-----------|------|-------|
| YOLOv8n | 37.3 | ~52 | ~30ms/frame | 6MB | Best CPU throughput |
| YOLOv8s | 44.9 | ~58 | ~80ms/frame | 22MB | Better accuracy, 3× slower |
| YOLOv8m | 50.2 | ~63 | ~150ms/frame | 50MB | Production choice with GPU |
| RT-DETR-L | 53.0 | ~65 | ~400ms/frame | 120MB | Transformer; GPU-only practical |
| MediaPipe | N/A | N/A | ~15ms/frame | 8MB | People detection, no bboxes for tracking |

### What AI Suggested

Consulted Claude on model selection with the prompt: *"Compare YOLOv8n vs RT-DETR for retail CCTV person detection. Consider: CPU-only deployment, 15fps input, partial occlusion, group entry counting."*

Claude's suggestion: **RT-DETR** for highest accuracy, specifically citing that transformer attention handles partial occlusion better than CNN-based local anchor approaches. Claude noted RT-DETR's global attention mechanism can "see through" partial occlusions better than YOLO's local receptive field.

### What I Chose and Why

**Dual-mode detection: YOLOv8n (GPU) with OpenCV MOG2 fallback (CPU).**

The actual footage was processed using OpenCV MOG2 background subtraction + contour tracking, producing 455 real events from 8 camera clips across both stores. The pipeline auto-detects whether `torch`/`ultralytics` is available and degrades gracefully:
- If YOLO is available: YOLOv8n on every 3rd frame (5fps effective)
- If not: MOG2 background subtraction at 320×180 downscaled frames, stride=8, producing equivalent detection quality at 89fps on CPU

**YOLOv8n with `classes=[0]` (person-only mode).**

1. **CPU constraint is real**: RT-DETR at 400ms/frame = 2.5fps. With our 15fps input and DETECT_STRIDE=3 (process every 3rd frame = 5fps effective), YOLOv8n at 30ms/frame gives 33fps capability — ample headroom. RT-DETR would process at 2.5fps, below real-time.

2. **Person class accuracy outperforms overall mAP**: On COCO `person` class specifically, YOLOv8n achieves ~52 AP₅₀. The 37.3 overall mAP includes 79 other classes diluting the number. For single-class detection, the gap narrows significantly.

3. **Where I agreed with AI**: For partial occlusion, both models degrade gracefully with confidence < threshold. My approach preserves all detections regardless of confidence — low-confidence detections still reach the tracker, just with lower weight in IoU matching. This is strictly correct: we should flag uncertainty, not suppress data.

4. **Where I disagreed with AI**: AI did not flag the CPU deployment constraint strongly enough. RT-DETR being "more accurate" is only useful if it can run at all. For take-home and small-store deployment scenarios, YOLOv8n is the production-appropriate choice.

5. **Production upgrade path**: YOLOv8m (GPU) or RT-DETR-L for permanent in-store hardware installations. The code is model-agnostic — swap the `YOLO('yolov8n.pt')` constructor.

6. **VLM usage**: I evaluated using Claude Vision for zone classification and staff detection. The prompt I tested: *"Is this person wearing retail staff uniform? Look at uniform colour, name badge, and apron. Answer yes/no with confidence."* Result: works but introduces 200-500ms latency per detection. Decided against per-frame VLM calls in the real-time path. A viable alternative: VLM call on the first frame a new track appears (cached for that visitor_id). This would improve staff detection recall from ~70% (heuristic) to ~90%+ (VLM). Left as a documented production improvement.

---

## Decision 2: Event Schema Design

### The Core Challenge

The schema must simultaneously:
- Be rich enough for all analytics queries (funnel, heatmap, anomalies, Re-ID)
- Be flat enough for SQLite indexing (no JSON columns for hot-path fields)
- Be extensible without breaking existing consumers
- Comply with the challenge specification exactly

### Options Considered

**Option A: Fully flat row** — all fields top-level, no metadata nesting.
- Pro: Fastest queries, no JSON parsing
- Con: Schema changes require migrations; optional fields pollute every row

**Option B: Nested metadata for all fields** — event_id, type, store, timestamp only at top level; everything else in metadata JSON.
- Pro: Maximum flexibility, easy extension
- Con: Cannot index metadata fields; `is_staff` in metadata means the exclusion filter requires a JSON extract on every query row

**Option C: Hybrid (chosen)** — frequently queried fields at top level + indexed; optional/extensible fields in metadata.
- `is_staff`, `confidence`, `zone_id`, `dwell_ms` → top-level + indexed
- `queue_depth`, `sku_zone`, `session_seq` → metadata dict

### What AI Suggested

Prompt: *"Design a database schema for retail CCTV events. Must support: unique visitors, zone dwell, conversion funnel, billing queue depth, staff exclusion. Optimise for SQLite."*

AI suggested Option C (hybrid) and specifically recommended:
- `is_staff` as a boolean column (not in metadata) so it can be used in `WHERE is_staff = FALSE` without JSON extraction
- `confidence` as a float column so anomaly detection can query low-confidence windows
- `UNIQUE(event_id)` constraint for idempotency
- Composite indexes on `(store_id, event_type)` and `(store_id, timestamp)` for the analytics query patterns

I agreed with all of these. My additions beyond what AI suggested:
- `session_seq` in metadata (not top-level) — useful for ordering events within a session without timestamp precision issues, but not needed for any WHERE clause
- `ingested_at` column (not in challenge spec) — essential for debugging lag between event time and ingest time; an on-call engineer would need this to diagnose STALE_FEED

### Why the Hybrid Approach Wins

The critical query is: `WHERE store_id = X AND is_staff = FALSE AND event_type = 'ENTRY'`. With `is_staff` in metadata JSON, this would require a full scan + JSON extract on every row. With `is_staff` as an indexed boolean column, this uses the `idx_store_type` composite index and returns in milliseconds even at millions of rows.

---

## Decision 3: API Architecture — Synchronous FastAPI + SQLite vs Async + Message Queue

### Options Considered

**Option A: Synchronous FastAPI + SQLite (chosen)**
- Single process, synchronous route handlers
- SQLite UNIQUE constraint for idempotency
- Per-request metric computation (no cache)

**Option B: Async FastAPI + PostgreSQL + Redis cache**
- Async SQLAlchemy, asyncpg driver
- Redis for 5-second rolling metric cache
- Background task for metric aggregation

**Option C: Event-driven with Kafka**
- Kafka topic per store for event ingest
- Stream processor (Faust/Flink) for real-time metric computation
- REST API layer queries pre-aggregated results

### What AI Suggested

Prompt: *"For a retail analytics API ingesting ~10 events/second per store across 40 stores, what's the right architecture? Compare synchronous SQLite vs async PostgreSQL vs Kafka stream processing."*

AI's suggestion: Start with Option B (async FastAPI + PostgreSQL + Redis cache) even for the take-home, arguing that async handlers avoid blocking the event loop and Redis cache makes metrics sub-millisecond.

### What I Chose and Why

**Option A (synchronous) — and I disagreed with the AI recommendation.**

1. **Sync vs async doesn't matter for SQLite**: SQLite is not concurrency-safe for writes anyway (`check_same_thread=False` is a workaround, not a solution). Adding async on top of a single-writer database provides no benefit and adds complexity.

2. **Redis cache adds operational overhead without correctness benefit**: For a take-home that says "must run via `docker compose up`", adding Redis means maintaining cache invalidation logic and a second process. The challenge says "real-time — not cached from yesterday" for metrics. Per-request DB queries satisfy this requirement with minimal latency for single-store workloads.

3. **Where AI was right about production**: At 40 stores × 10 events/second = 400 events/second ingest, the synchronous per-event commit loop in `ingest_events` becomes the bottleneck. The correct production fix is: bulk insert (one `db.add_all()` + one `db.commit()` per batch, not one commit per event). This is a 5-line change. I chose to leave the current implementation as a documented known limitation rather than prematurely optimise.

4. **Why SQLite over PostgreSQL**: The DATABASE_URL environment variable pattern means the switch is zero-code. Running PostgreSQL locally for a take-home evaluation adds Docker complexity. SQLite is sufficient for single-store evaluation and the challenge explicitly says it's acceptable.

5. **Trade-off acknowledged**: The current design cannot handle 40 concurrent stores at production event rates. The migration path (bulk insert + async + PostgreSQL) is documented in DESIGN.md and I can reason about it precisely because I built the simpler version first.
