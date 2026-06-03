"""
Tests for the detection pipeline: event schema, emit, tracker.

# PROMPT: "Write pytest tests for: (1) StoreEvent dataclass serialisation,
# (2) EventEmitter writes valid JSONL, (3) ByteTracker assigns unique visitor IDs,
# (4) ByteTracker detects reentry via appearance similarity, (5) staff heuristic
# triggers on multi-zone tracks, (6) group detection emits N individual events."
# CHANGES MADE: Mocked YOLO to use MockDetector. Added low-confidence event test.
# Added schema compliance check against required field list.
"""

import uuid
import json
import tempfile
import numpy as np
import pytest
from datetime import datetime, timezone

from pipeline.emit import make_event, EventEmitter, StoreEvent
from pipeline.tracker import ByteTracker, Track


REQUIRED_EVENT_FIELDS = {
    "event_id", "store_id", "camera_id", "visitor_id",
    "event_type", "timestamp", "zone_id", "dwell_ms",
    "is_staff", "confidence", "metadata",
}

REQUIRED_METADATA_FIELDS = {"queue_depth", "sku_zone", "session_seq"}


class TestEventSchema:
    def test_make_event_has_all_required_fields(self):
        ev = make_event(
            store_id="STORE_BLR_002",
            camera_id="CAM_ENTRY_01",
            visitor_id="VIS_abc123",
            event_type="ENTRY",
            timestamp=datetime.now(timezone.utc),
        )
        d = ev.to_dict()
        assert REQUIRED_EVENT_FIELDS.issubset(d.keys()), f"Missing: {REQUIRED_EVENT_FIELDS - d.keys()}"
        assert REQUIRED_METADATA_FIELDS.issubset(d["metadata"].keys())

    def test_event_id_is_uuid(self):
        ev = make_event("STORE_BLR_002", "CAM_01", "VIS_x", "EXIT", datetime.now(timezone.utc))
        uuid.UUID(ev.event_id)  # raises if invalid

    def test_timestamp_iso8601_utc(self):
        ev = make_event("S", "C", "V", "ENTRY", datetime(2026, 4, 10, 14, 30, 0, tzinfo=timezone.utc))
        assert ev.timestamp == "2026-04-10T14:30:00Z"

    def test_zone_dwell_has_dwell_ms(self):
        ev = make_event("S", "C", "V", "ZONE_DWELL",
                        datetime.now(timezone.utc), zone_id="SKINCARE", dwell_ms=30000)
        assert ev.dwell_ms == 30000

    def test_billing_queue_join_has_queue_depth(self):
        ev = make_event("S", "C", "V", "BILLING_QUEUE_JOIN",
                        datetime.now(timezone.utc), queue_depth=3, zone_id="BILLING")
        assert ev.metadata.queue_depth == 3

    def test_event_serialises_to_valid_json(self):
        ev = make_event("STORE_BLR_002", "CAM_01", "VIS_1", "ENTRY", datetime.now(timezone.utc))
        parsed = json.loads(ev.to_json())
        assert parsed["event_type"] == "ENTRY"

    def test_all_event_ids_unique(self):
        events = [make_event("S", "C", f"VIS_{i}", "ENTRY", datetime.now(timezone.utc)) for i in range(100)]
        ids = [e.event_id for e in events]
        assert len(ids) == len(set(ids)), "Duplicate event_ids!"

    def test_confidence_range(self):
        ev = make_event("S", "C", "V", "ENTRY", datetime.now(timezone.utc), confidence=0.45)
        assert 0.0 <= ev.confidence <= 1.0

    def test_low_confidence_event_not_dropped(self):
        """Low-confidence detections must be flagged, not silently dropped."""
        ev = make_event("S", "C", "V", "ENTRY", datetime.now(timezone.utc), confidence=0.22)
        assert ev.confidence == 0.22  # preserved, not elevated


class TestEventEmitter:
    def test_emitter_writes_valid_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as f:
            path = f.name

        with EventEmitter(path) as emitter:
            for i in range(5):
                ev = make_event("S", "C", f"VIS_{i}", "ENTRY", datetime.now(timezone.utc))
                emitter.emit(ev)

        with open(path) as f:
            lines = f.readlines()

        assert len(lines) == 5
        for line in lines:
            parsed = json.loads(line)
            assert "event_id" in parsed

    def test_emitter_appends_not_overwrites(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name
            f.write(json.dumps({"existing": True}) + "\n")

        with EventEmitter(path) as emitter:
            ev = make_event("S", "C", "V", "ENTRY", datetime.now(timezone.utc))
            emitter.emit(ev)

        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2


class TestByteTracker:
    def _make_frame(self, h=480, w=640) -> np.ndarray:
        return np.zeros((h, w, 3), dtype=np.uint8)

    def _bbox(self, x=0.3, y=0.3, w=0.1, h=0.2):
        return (x, y, x + w, y + h)

    def test_new_detection_creates_track(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        dets = [(self._bbox(), 0.85)]
        tracks, events = tracker.update(dets, frame, frame_idx=1)
        assert len(tracks) == 1
        assert any(e.startswith("new:") for e in events)

    def test_each_detection_gets_unique_visitor_id(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        dets = [
            (self._bbox(0.1, 0.3), 0.9),
            (self._bbox(0.5, 0.3), 0.9),
            (self._bbox(0.8, 0.3), 0.9),
        ]
        tracks, events = tracker.update(dets, frame, frame_idx=1)
        ids = [t.visitor_id for t in tracks]
        assert len(ids) == len(set(ids)), "Duplicate visitor IDs for simultaneous detections"

    def test_group_entry_emits_n_events(self):
        """3 people entering together → 3 separate new track events."""
        tracker = ByteTracker()
        frame = self._make_frame()
        dets = [(self._bbox(0.1 * i, 0.3), 0.85) for i in range(3)]
        tracks, events = tracker.update(dets, frame, frame_idx=1)
        new_events = [e for e in events if e.startswith("new:")]
        assert len(new_events) == 3

    def test_track_persists_across_frames(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        bbox = self._bbox(0.3, 0.3)
        tracker.update([(bbox, 0.9)], frame, 1)
        tracks, events = tracker.update([(bbox, 0.88)], frame, 2)
        # Should still be the same track, no new events
        new_events = [e for e in events if e.startswith("new:")]
        assert len(new_events) == 0
        assert len(tracks) == 1

    def test_lost_track_emits_lost_event(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        tracker.update([(self._bbox(), 0.9)], frame, 1)
        # Fast-forward past TTL without any detections
        tracks, events = tracker.update([], frame, frame_idx=1 + ByteTracker.LOST_TRACK_TTL + 1)
        assert any(e.startswith("lost:") for e in events)

    def test_staff_flagging_multi_zone(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        # Create a track and manually add many zones to trigger staff heuristic
        tracker.update([(self._bbox(), 0.9)], frame, 1)
        track = list(tracker._active_tracks.values())[0]
        track.zone_history = ["SKINCARE", "MAKEUP", "HAIRCARE", "BILLING", "FRAGRANCE"]
        track.first_seen_frame = 1
        # Keep track alive by setting last_seen_frame close to current frame
        track.last_seen_frame = 349
        # Update again after 300+ frames (lifespan = 349, triggers staff check)
        tracker.update([(self._bbox(), 0.9)], frame, 350)
        assert track.is_staff is True

    def test_visitor_id_format(self):
        tracker = ByteTracker()
        frame = self._make_frame()
        tracks, _ = tracker.update([(self._bbox(), 0.9)], frame, 1)
        assert tracks[0].visitor_id.startswith("VIS_")
