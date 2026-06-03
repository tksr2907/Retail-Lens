"""
Extended tests for hourly, journey, revenue, health, and additional API endpoints.

# PROMPT: "Write pytest tests for hourly traffic, journey paths, revenue, health,
# summary, export, compare, confidence endpoints. Cover edge cases: empty store,
# all-staff, zero purchases, reentry in funnel, 24-hour bucketing."
# CHANGES MADE: Fixed hourly test to count all 24 hours (not just 10-22).
# Added all-staff metrics test. Fixed compare empty-ids test.
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from tests.conftest import make_event, seed_visitors, STORE_ID, ts, NOW


class TestHourly:
    def test_hourly_returns_structure(self, client):
        seed_visitors(client, 5, 2)
        r = client.get(f"/stores/{STORE_ID}/hourly")
        assert r.status_code == 200
        body = r.json()
        assert "store_id" in body
        assert "hourly_visitors" in body
        assert "peak_hour" in body
        assert "total_visitors" in body

    def test_hourly_empty_store(self, client):
        r = client.get("/stores/STORE_EMPTY_HOURLY/hourly")
        assert r.status_code == 200
        body = r.json()
        assert body["total_visitors"] == 0
        assert body["peak_hour"] is not None
        assert isinstance(body["hourly_visitors"], dict)

    def test_hourly_counts_entries(self, client):
        events = [make_event("ENTRY", visitor_id=f"VIS_HR_{i:04x}", offset_min=i) for i in range(10)]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/hourly")
        body = r.json()
        assert body["total_visitors"] == 10

    def test_hourly_with_date_param(self, client):
        seed_visitors(client, 3, 1)
        date_str = NOW.strftime("%Y-%m-%d")
        r = client.get(f"/stores/{STORE_ID}/hourly?date={date_str}")
        assert r.status_code == 200
        assert r.json()["date"] == date_str

    def test_hourly_excludes_staff(self, client):
        events = [
            make_event("ENTRY", visitor_id="VIS_STAFF_HR", is_staff=True),
            make_event("ENTRY", visitor_id="VIS_CUST_HR"),
        ]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/hourly")
        assert r.json()["total_visitors"] == 1

    def test_hourly_all_24_hours_present(self, client):
        r = client.get("/stores/STORE_EMPTY_ALL_HOURS/hourly")
        body = r.json()
        hourly = body["hourly_visitors"]
        assert "00:00" in hourly
        assert "10:00" in hourly
        assert "22:00" in hourly
        assert len(hourly) == 24


class TestJourney:
    def test_journey_returns_structure(self, client):
        seed_visitors(client, 5, 2)
        r = client.get(f"/stores/{STORE_ID}/journey")
        assert r.status_code == 200
        body = r.json()
        assert "top_paths" in body
        assert "top_transitions" in body
        assert "avg_zones_per_visit" in body
        assert "total_sessions_with_zones" in body

    def test_journey_empty_store(self, client):
        r = client.get("/stores/STORE_EMPTY_JOURNEY/journey")
        assert r.status_code == 200
        body = r.json()
        assert body["total_sessions_with_zones"] == 0
        assert body["top_paths"] == []
        assert body["top_transitions"] == []
        assert body["avg_zones_per_visit"] == 0.0

    def test_journey_detects_paths(self, client):
        vid = "VIS_PATH_001"
        events = [
            make_event("ENTRY", visitor_id=vid),
            make_event("ZONE_ENTER", visitor_id=vid, zone_id="SKINCARE", offset_min=1),
            make_event("ZONE_ENTER", visitor_id=vid, zone_id="MAKEUP", offset_min=2),
            make_event("ZONE_ENTER", visitor_id=vid, zone_id="BILLING", offset_min=3),
        ]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/journey")
        body = r.json()
        assert body["total_sessions_with_zones"] >= 1
        all_paths = [p["path"] for p in body["top_paths"]]
        assert any("SKINCARE" in p for p in all_paths)

    def test_journey_counts_transitions(self, client):
        for i in range(5):
            vid = f"VIS_TRANS_{i:04x}"
            events = [
                make_event("ZONE_ENTER", visitor_id=vid, zone_id="SKINCARE", offset_min=i),
                make_event("ZONE_ENTER", visitor_id=vid, zone_id="BILLING", offset_min=i + 1),
            ]
            client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/journey")
        transitions = r.json()["top_transitions"]
        assert len(transitions) >= 1
        top = transitions[0]
        assert top["from_zone"] == "SKINCARE"
        assert top["to_zone"] == "BILLING"
        assert top["count"] == 5


class TestRevenue:
    def test_revenue_returns_structure(self, client):
        seed_visitors(client, 5, 2)
        r = client.get(f"/stores/{STORE_ID}/revenue")
        assert r.status_code == 200
        body = r.json()
        for field in ["store_id", "total_gmv_inr", "total_transactions",
                      "avg_basket_value_inr", "unique_visitors", "conversion_rate_pos"]:
            assert field in body, f"Missing field: {field}"

    def test_revenue_empty_store(self, client):
        r = client.get("/stores/STORE_EMPTY_REV/revenue")
        assert r.status_code == 200
        body = r.json()
        assert body["unique_visitors"] == 0
        assert body["revenue_per_visitor_inr"] == 0.0
        assert body["conversion_rate_pos"] == 0.0

    def test_revenue_conversion_rate_range(self, client):
        seed_visitors(client, 10, 4)
        r = client.get(f"/stores/{STORE_ID}/revenue")
        assert 0.0 <= r.json()["conversion_rate_pos"] <= 1.0

    def test_revenue_with_date_param(self, client):
        seed_visitors(client, 3, 1)
        date_str = NOW.strftime("%Y-%m-%d")
        r = client.get(f"/stores/{STORE_ID}/revenue?date={date_str}")
        assert r.status_code == 200


class TestHealth:
    def test_health_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_valid_structure(self, client):
        r = client.get("/health")
        body = r.json()
        assert "status" in body
        assert "service" in body
        assert "stores" in body
        assert "as_of" in body
        assert body["service"] == "store-intelligence-api"

    def test_health_overall_status_valid(self, client):
        r = client.get("/health")
        assert r.json()["status"] in ("OK", "DEGRADED")

    def test_health_store_entry_valid(self, client):
        seed_visitors(client, 5, 2)
        r = client.get("/health")
        body = r.json()
        for store in body["stores"]:
            assert "store_id" in store
            assert "status" in store
            assert store["status"] in ("OK", "STALE_FEED", "NO_DATA")

    def test_health_no_stores_returns_valid(self, client):
        r = client.get("/health")
        body = r.json()
        assert isinstance(body["stores"], list)
        assert body["status"] in ("OK", "DEGRADED")

    def test_health_version_present(self, client):
        r = client.get("/health")
        assert "version" in r.json()


class TestSummary:
    def test_summary_returns_all_sections(self, client):
        seed_visitors(client, 10, 4)
        r = client.get(f"/stores/{STORE_ID}/summary")
        assert r.status_code == 200
        body = r.json()
        for section in ["metrics", "funnel", "anomalies", "heatmap", "revenue"]:
            assert section in body, f"Missing section: {section}"
        assert "store_id" in body
        assert "health_status" in body

    def test_summary_empty_store_no_crash(self, client):
        r = client.get("/stores/STORE_EMPTY_SUMM/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["metrics"]["unique_visitors"] == 0

    def test_summary_health_status_field(self, client):
        r = client.get(f"/stores/{STORE_ID}/summary")
        body = r.json()
        assert body["health_status"] in ("OK", "WARN", "CRITICAL")


class TestExport:
    def test_export_json_returns_structure(self, client):
        seed_visitors(client, 5, 2)
        r = client.get(f"/stores/{STORE_ID}/export?format=json")
        assert r.status_code == 200
        body = r.json()
        assert "events" in body
        assert "total_events" in body
        assert isinstance(body["events"], list)

    def test_export_csv_returns_text(self, client):
        seed_visitors(client, 3, 1)
        r = client.get(f"/stores/{STORE_ID}/export?format=csv")
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")

    def test_export_empty_store(self, client):
        r = client.get("/stores/STORE_EMPTY_EXP/export?format=json")
        assert r.status_code == 200
        assert r.json()["total_events"] == 0


class TestConfidence:
    def test_confidence_returns_structure(self, client):
        events = [make_event("ENTRY", confidence=c) for c in [0.9, 0.85, 0.7, 0.55, 0.3]]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/confidence")
        assert r.status_code == 200
        body = r.json()
        for field in ["total_events", "avg_confidence", "buckets", "low_confidence_pct"]:
            assert field in body

    def test_confidence_empty_store(self, client):
        r = client.get("/stores/STORE_EMPTY_CONF/confidence")
        assert r.status_code == 200
        body = r.json()
        assert body["total_events"] == 0
        assert body["avg_confidence"] == 0

    def test_confidence_buckets_sum_to_total(self, client):
        events = [make_event("ENTRY", confidence=0.4),
                  make_event("ENTRY", confidence=0.6),
                  make_event("ENTRY", confidence=0.8),
                  make_event("ENTRY", confidence=0.9),
                  make_event("ENTRY", confidence=0.97)]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/confidence")
        body = r.json()
        bucket_sum = sum(body["buckets"].values())
        assert bucket_sum == body["total_events"]


class TestCompare:
    def test_compare_multiple_stores(self, client):
        for store in [STORE_ID, "STORE_BLR_003"]:
            events = [{"event_id": str(uuid.uuid4()), "store_id": store,
                       "camera_id": "CAM_ENTRY_01", "visitor_id": f"VIS_{i:06x}",
                       "event_type": "ENTRY", "timestamp": ts(i), "zone_id": None,
                       "dwell_ms": 0, "is_staff": False, "confidence": 0.9,
                       "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}}
                      for i in range(5)]
            client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/compare?ids={STORE_ID},STORE_BLR_003")
        assert r.status_code == 200
        body = r.json()
        assert "stores" in body
        assert len(body["stores"]) == 2
        assert "best_performer" in body
        assert "chain_avg_conversion" in body

    def test_compare_single_store(self, client):
        r = client.get(f"/stores/compare?ids={STORE_ID}")
        body = r.json()
        assert len(body["stores"]) == 1
        assert body["stores"][0]["rank"] == 1

    def test_compare_empty_ids(self, client):
        r = client.get("/stores/compare?ids=")
        assert r.status_code == 400


class TestTopLevelMetrics:
    def test_top_level_metrics_returns_structure(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        body = r.json()
        assert "store_count" in body
        assert "total_unique_visitors" in body
        assert "avg_conversion_rate" in body
        assert "stores" in body

    def test_top_level_metrics_no_crash_empty_db(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200
        body = r.json()
        assert body["total_unique_visitors"] >= 0


class TestIngestEdgeCases:
    def test_ingest_reentry_event_type(self, client):
        vid = "VIS_REENTRY_EXT"
        events = [
            make_event("ENTRY", visitor_id=vid),
            make_event("EXIT", visitor_id=vid, offset_min=5),
            make_event("REENTRY", visitor_id=vid, offset_min=30),
        ]
        r = client.post("/events/ingest", json={"events": events})
        assert r.status_code == 200
        assert r.json()["accepted"] == 3

    def test_ingest_high_confidence_preserved(self, client):
        ev = make_event("ENTRY", confidence=0.99)
        r = client.post("/events/ingest", json={"events": [ev]})
        assert r.status_code == 200

    def test_ingest_minimum_valid_confidence(self, client):
        ev = make_event("ENTRY", confidence=0.0)
        r = client.post("/events/ingest", json={"events": [ev]})
        assert r.status_code == 200

    def test_ingest_all_zone_ids_accepted(self, client):
        zones = ["SKINCARE", "MAKEUP", "HAIRCARE", "BATH_BODY", "FRAGRANCE", "PERSONAL_CARE", "BILLING"]
        events = [make_event("ZONE_ENTER", zone_id=z) for z in zones]
        r = client.post("/events/ingest", json={"events": events})
        assert r.status_code == 200
        assert r.json()["accepted"] == len(zones)

    def test_funnel_all_staff_no_crash(self, client):
        events = [make_event("ENTRY", visitor_id=f"VIS_S{i}", is_staff=True) for i in range(10)]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/funnel")
        assert r.status_code == 200
        assert r.json()["total_sessions"] == 0

    def test_metrics_all_staff_clip(self, client):
        events = [make_event("ENTRY", visitor_id=f"VIS_STAFF_{i}", is_staff=True) for i in range(20)]
        client.post("/events/ingest", json={"events": events})
        r = client.get(f"/stores/{STORE_ID}/metrics")
        body = r.json()
        assert body["unique_visitors"] == 0
        assert body["conversion_rate"] == 0.0
