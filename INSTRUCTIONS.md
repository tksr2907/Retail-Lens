# Instructions to Run

**Prerequisites:** Docker and Docker Compose installed.

---

## Option 1 — API + Dashboard (seeded data, no videos needed)

```bash
git clone <repo-url>
cd RetailLens
docker compose up
```

- API: http://localhost:8000
- Interactive Dashboard: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

On first startup the system auto-seeds Brigade Road store data with timestamps re-anchored to today, so all metrics are live immediately — no manual setup needed.

---

## Option 2 — Full YOLO Detection Pipeline (requires video files)

Place `CAM 1.mp4` through `CAM 5.mp4` in the `data/` directory, then:

```bash
# Quick test (first 30 seconds of each clip, ~2 min on CPU)
MAX_FRAMES=450 docker compose --profile pipeline up

# Full run (all footage)
docker compose --profile pipeline up
```

---

## Option 3 — Run Tests

> **Note:** Use this install command instead of `pip install -r requirements.txt` — the full requirements pulls PyTorch (~800MB) which tests don't need. Tests run entirely on in-memory SQLite with no video files required.

```bash
pip install fastapi uvicorn pydantic sqlalchemy structlog python-multipart httpx pytest pytest-asyncio pytest-cov
pytest --tb=short
```

51 unit + integration tests, all passing. Includes API assertion suite covering all 10 key endpoints.

---

## Key Endpoints to Try

| URL | What you'll see |
|---|---|
| `/stores/brigade-road/metrics` | Visitors, conversion rate, dwell time |
| `/stores/brigade-road/funnel` | Entry → Zone → Billing → Purchase funnel |
| `/stores/brigade-road/anomalies` | Live anomaly alerts with severity |
| `/stores/brigade-road/heatmap` | Zone activity heatmap |
| `/stores/brigade-road/revenue` | POS-correlated GMV and basket value |
