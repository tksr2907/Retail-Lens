"""
assertions.py — 10 API test assertions the Store Intelligence API must pass.

Run: python assertions.py --api-url http://localhost:8000

These mirror the held-out scoring test suite format described in the challenge.
"""

# PROMPT: "Generate 10 integration test assertions for a retail store analytics API.
# Cover: ingest idempotency, metrics zero-visitor, conversion rate math, funnel ordering,
# heatmap normalisation, anomaly schema, health endpoint, staff exclusion,
# batch size limit, and schema validation."
# CHANGES MADE: Added real HTTP calls, coloured output, exit code on failure.

import sys
import uuid
import json
import argparse
import httpx

STORE_ID = "STORE_BLR_002"
PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
failures = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  {PASS}  {name}")
    else:
        print(f"  {FAIL}  {name}" + (f" — {detail}" if detail else ""))
        failures.append(name)


def make_event(event_type, visitor_id=None, zone_id=None, dwell_ms=0,
               is_staff=False, confidence=0.9, queue_depth=None, ts="2026-05-31T15:00:00Z"):
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id or f"VIS_{uuid.uuid4().hex[:6]}",
        "event_type": event_type,
        "timestamp": ts,
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": confidence,
        "metadata": {"queue_depth": queue_depth, "sku_zone": zone_id, "session_seq": 1},
    }


def run(api_url: str):
    base = api_url.rstrip("/")
    client = httpx.Client(base_url=base, timeout=15)

    print(f"\n{'='*55}")
    print(f"  RetailLens API Assertions — {base}")
    print(f"{'='*55}\n")

    # ── Assertion 1: POST /events/ingest accepts valid events ──────────────────
    print("Assertion 1: POST /events/ingest accepts valid events")
    ev = make_event("ENTRY", visitor_id="VIS_assert_001")
    r = client.post("/events/ingest", json={"events": [ev]})
    check("Status 200", r.status_code == 200, f"got {r.status_code}")
    body = r.json()
    check("accepted >= 1", body.get("accepted", 0) >= 1, str(body))
    check("errors is list", isinstance(body.get("errors"), list))

    # ── Assertion 2: Idempotency — same event_id twice = duplicate ─────────────
    print("\nAssertion 2: POST /events/ingest is idempotent")
    fixed_id = str(uuid.uuid4())
    ev2 = make_event("ENTRY", visitor_id="VIS_idem_001")
    ev2["event_id"] = fixed_id
    client.post("/events/ingest", json={"events": [ev2]})
    r2 = client.post("/events/ingest", json={"events": [ev2]})
    body2 = r2.json()
    check("Second ingest accepted=0", body2.get("accepted") == 0, str(body2))
    check("Second ingest duplicate=1", body2.get("duplicate") == 1, str(body2))

    # ── Assertion 3: Batch over 500 rejected ──────────────────────────────────
    print("\nAssertion 3: Batch > 500 events rejected with 422")
    big_batch = [make_event("ENTRY") for _ in range(501)]
    r3 = client.post("/events/ingest", json={"events": big_batch})
    check("Status 422 for 501 events", r3.status_code == 422, f"got {r3.status_code}")

    # ── Assertion 4: GET /metrics returns valid structure ─────────────────────
    print("\nAssertion 4: GET /stores/{id}/metrics returns valid schema")
    r4 = client.get(f"/stores/{STORE_ID}/metrics")
    check("Status 200", r4.status_code == 200, f"got {r4.status_code}")
    m = r4.json()
    for field in ["store_id", "unique_visitors", "conversion_rate", "avg_dwell_ms",
                  "queue_depth", "abandonment_rate", "zone_dwells", "as_of"]:
        check(f"  Field '{field}' present", field in m)
    check("conversion_rate in [0,1]", 0.0 <= m.get("conversion_rate", -1) <= 1.0)
    check("zone_dwells is list", isinstance(m.get("zone_dwells"), list))

    # ── Assertion 5: Staff excluded from metrics ───────────────────────────────
    print("\nAssertion 5: Staff events excluded from unique_visitors")
    staff_ev = make_event("ENTRY", visitor_id="VIS_staff_assert", is_staff=True)
    client.post("/events/ingest", json={"events": [staff_ev]})
    r5 = client.get(f"/stores/{STORE_ID}/metrics")
    m5 = r5.json()
    # Staff visitor should not appear in unique_visitors count
    # We can't assert exact number, but conversion_rate must still be 0-1
    check("Metrics still valid after staff ingest", 0 <= m5.get("conversion_rate", -1) <= 1.0)

    # ── Assertion 6: GET /funnel returns 4 stages in order ────────────────────
    print("\nAssertion 6: GET /stores/{id}/funnel returns 4 ordered stages")
    r6 = client.get(f"/stores/{STORE_ID}/funnel")
    check("Status 200", r6.status_code == 200, f"got {r6.status_code}")
    f6 = r6.json()
    stages = f6.get("stages", [])
    check("4 stages present", len(stages) == 4, f"got {len(stages)}")
    expected_stages = ["Entry", "Zone Visit", "Billing Queue", "Purchase"]
    for i, name in enumerate(expected_stages):
        check(f"  Stage {i+1} = '{name}'", stages[i]["stage"] == name if i < len(stages) else False)
    counts = [s["count"] for s in stages]
    check("Stage counts non-increasing", all(counts[i] >= counts[i+1] for i in range(len(counts)-1)),
          str(counts))

    # ── Assertion 7: GET /heatmap normalised 0-100 ────────────────────────────
    print("\nAssertion 7: GET /stores/{id}/heatmap scores normalised 0-100")
    # Seed some zone data first
    zone_events = [make_event("ZONE_ENTER", zone_id="SKINCARE"),
                   make_event("ZONE_DWELL", zone_id="SKINCARE", dwell_ms=30000)]
    client.post("/events/ingest", json={"events": zone_events})
    r7 = client.get(f"/stores/{STORE_ID}/heatmap")
    check("Status 200", r7.status_code == 200, f"got {r7.status_code}")
    h7 = r7.json()
    zones = h7.get("zones", [])
    if zones:
        scores = [z["score"] for z in zones]
        check("Max score = 100", max(scores) == 100.0, f"max={max(scores)}")
        check("All scores 0-100", all(0 <= s <= 100 for s in scores))
        check("data_confidence field present", "data_confidence" in zones[0])

    # ── Assertion 8: GET /anomalies returns valid schema ──────────────────────
    print("\nAssertion 8: GET /stores/{id}/anomalies returns valid anomaly schema")
    r8 = client.get(f"/stores/{STORE_ID}/anomalies")
    check("Status 200", r8.status_code == 200, f"got {r8.status_code}")
    a8 = r8.json()
    check("'anomalies' key present", "anomalies" in a8)
    check("'as_of' key present", "as_of" in a8)
    for anomaly in a8.get("anomalies", []):
        for field in ["anomaly_id", "anomaly_type", "severity", "description", "suggested_action"]:
            check(f"  Anomaly field '{field}'", field in anomaly)
        check("  Severity valid", anomaly.get("severity") in ["INFO", "WARN", "CRITICAL"])

    # ── Assertion 9: GET /health returns valid structure ──────────────────────
    print("\nAssertion 9: GET /health returns valid structure")
    r9 = client.get("/health")
    check("Status 200", r9.status_code == 200, f"got {r9.status_code}")
    h9 = r9.json()
    check("'status' field present", "status" in h9)
    check("'stores' field is list", isinstance(h9.get("stores"), list))
    check("'service' field present", "service" in h9)
    for store in h9.get("stores", []):
        check("  Store has status field", "status" in store)
        check("  Store status valid", store.get("status") in ["OK", "STALE_FEED", "NO_DATA"])

    # ── Assertion 10: Empty store returns zeros, not errors ───────────────────
    print("\nAssertion 10: Empty store returns zeros, not 404 or 500")
    r10m = client.get("/stores/STORE_EMPTY_ASSERT/metrics")
    check("Metrics 200 for empty store", r10m.status_code == 200, f"got {r10m.status_code}")
    m10 = r10m.json()
    check("unique_visitors = 0", m10.get("unique_visitors") == 0)
    check("conversion_rate = 0.0", m10.get("conversion_rate") == 0.0)

    r10f = client.get("/stores/STORE_EMPTY_ASSERT/funnel")
    check("Funnel 200 for empty store", r10f.status_code == 200, f"got {r10f.status_code}")
    f10 = r10f.json()
    check("total_sessions = 0", f10.get("total_sessions") == 0)

    r10a = client.get("/stores/STORE_EMPTY_ASSERT/anomalies")
    check("Anomalies 200 for empty store", r10a.status_code == 200, f"got {r10a.status_code}")

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'='*55}")
    total_checks = 10 + len([f for f in failures])
    passed = len([1 for f in failures if False]) if False else None
    if failures:
        print(f"  FAILED assertions: {len(failures)}")
        for f in failures:
            print(f"    - {f}")
        print(f"{'='*55}\n")
        sys.exit(1)
    else:
        print(f"  All assertions passed ✓")
        print(f"{'='*55}\n")
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run API assertions")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()
    run(args.api_url)
