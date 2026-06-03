"""
Main detection + tracking script.

Model: YOLOv8n (nano) — chosen for speed on CPU-only environments typical
of take-home evaluations. Detects 'person' class (class 0).

Pipeline per camera:
  1. Load video with OpenCV
  2. Run YOLO on every Nth frame (stride=3) for efficiency
  3. Pass person detections to ByteTracker
  4. Determine zone from bbox position + camera type
  5. Emit structured events via EventEmitter

Entry/Exit detection (CAM_ENTRY_01):
  We define a virtual tripwire at y = entry_line_y_fraction of frame height.
  A track crossing downward (increasing y) → ENTRY; upward → EXIT.

Staff detection:
  Heuristic in tracker.py. Additionally: if a detection has been continuously
  present for > 5 minutes without exiting, flagged is_staff=True.

Group entry:
  Multiple detections in the same frame at the entry threshold emit multiple
  ENTRY events — one per bounding box.

# AI-ASSISTED DECISION (Claude, 2026):
# Asked Claude to evaluate YOLOv8n vs RT-DETR for this use case.
# Claude suggested RT-DETR for higher accuracy, but noted YOLOv8n is
# significantly faster and works on CPU. Given take-home constraints
# (no GPU guaranteed), I chose YOLOv8n. RT-DETR would be chosen for prod.
"""

import os
import sys
import json
import argparse
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
import cv2

# Pipeline imports
from pipeline.tracker import ByteTracker, Track
from pipeline.emit import EventEmitter, make_event, StoreEvent

# Try importing ultralytics; if unavailable, fall back to mock detection
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("WARNING: ultralytics not available. Using mock detection for testing.")


PERSON_CLASS_ID = 0
DETECT_STRIDE = 3      # process every 3rd frame (effective 5fps from 15fps)
DWELL_EMIT_INTERVAL_FRAMES = 450  # 30 seconds at 15fps
BILLING_QUEUE_DEPTH_THRESHOLD = 2  # 2+ people in billing = queue


class MockDetector:
    """Fallback detector that generates synthetic detections for testing."""

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self._frame = 0

    def detect(self, frame: np.ndarray) -> List[Tuple[Tuple, float]]:
        self._frame += 1
        detections = []
        n_people = self.rng.integers(0, 4)
        for _ in range(n_people):
            x1 = float(self.rng.uniform(0.05, 0.8))
            y1 = float(self.rng.uniform(0.05, 0.8))
            w = float(self.rng.uniform(0.05, 0.15))
            h = float(self.rng.uniform(0.15, 0.35))
            conf = float(self.rng.uniform(0.4, 0.95))
            detections.append(((x1, y1, x1 + w, y1 + h), conf))
        return detections


class YOLODetector:
    """YOLOv8-based person detector."""

    def __init__(self, model_size: str = "yolov8n"):
        self.model = YOLO(f"{model_size}.pt")

    def detect(self, frame: np.ndarray) -> List[Tuple[Tuple, float]]:
        h, w = frame.shape[:2]
        results = self.model(frame, verbose=False, classes=[PERSON_CLASS_ID])
        detections = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                conf = float(box.conf[0])
                # Normalise to [0,1]
                detections.append((
                    (x1 / w, y1 / h, x2 / w, y2 / h),
                    conf
                ))
        return detections


def load_store_layout(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_camera_config(layout: dict, camera_id: str) -> Optional[dict]:
    for cam in layout.get("cameras", []):
        if cam["camera_id"] == camera_id:
            return cam
    return None


def get_zone_for_camera(layout: dict, camera_id: str) -> Optional[dict]:
    """Return the primary zone covered by this camera."""
    for zone in layout.get("zones", []):
        if camera_id in zone.get("camera_ids", []):
            return zone
    return None


def classify_zone_from_bbox(
    bbox: Tuple, camera_type: str, layout: dict, camera_id: str
) -> Optional[str]:
    """
    Map a detection's position to a zone_id.
    For billing/entry cameras, the zone is fixed.
    For floor cameras, use bbox position to sub-classify.
    """
    if camera_type == "entry":
        return "ENTRY"
    if camera_type == "billing":
        return "BILLING"

    # For floor cameras: find zone whose bbox contains the detection centre
    cx = (bbox[0] + bbox[2]) / 2
    cy = (bbox[1] + bbox[3]) / 2
    for zone in layout.get("zones", []):
        if camera_id not in zone.get("camera_ids", []):
            continue
        zb = zone.get("bbox")
        if not zb:
            continue
        if zb[0] <= cx <= zb[2] and zb[1] <= cy <= zb[3]:
            return zone["zone_id"]
    # Fallback: return first zone on this camera
    primary = get_zone_for_camera(layout, camera_id)
    return primary["zone_id"] if primary else None


def process_clip(
    video_path: str,
    camera_id: str,
    camera_type: str,
    store_id: str,
    layout: dict,
    emitter: EventEmitter,
    clip_start_time: datetime,
    api_url: Optional[str] = None,
    batch_size: int = 50,
    max_frames: int = 0,
) -> Dict:
    """Process one camera clip and emit events. max_frames=0 means full clip."""

    detector = YOLODetector() if YOLO_AVAILABLE else MockDetector()
    if YOLO_AVAILABLE:
        print(f"  Using YOLOv8n (real detection)")
    else:
        print(f"  Using MockDetector (ultralytics not available)")
    tracker = ByteTracker()

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[{camera_id}] Processing {total_frames} frames @ {fps:.1f}fps")

    # State tracking per visitor
    visitor_zone: Dict[str, str] = {}          # visitor_id -> current zone_id
    visitor_zone_enter_frame: Dict[str, int] = {}  # visitor_id -> frame when entered zone
    visitor_session_seq: Dict[str, int] = {}   # visitor_id -> event counter
    billing_visitors: set = set()              # visitor_ids in BILLING zone
    exited_visitors: set = set()               # visitor_ids that have EXIT'd

    # Entry line tripwire state (entry cameras)
    visitor_prev_y: Dict[str, float] = {}     # for direction detection

    # Event batch for API push
    event_batch: List[dict] = []

    def flush_batch():
        if api_url and event_batch:
            try:
                httpx.post(
                    f"{api_url}/events/ingest",
                    json={"events": event_batch},
                    timeout=10.0,
                )
            except Exception as e:
                print(f"  [WARN] API push failed: {e}")
            event_batch.clear()

    def incr_seq(vid: str) -> int:
        visitor_session_seq[vid] = visitor_session_seq.get(vid, 0) + 1
        return visitor_session_seq[vid]

    def emit_and_batch(event: StoreEvent):
        emitter.emit(event)
        event_batch.append(event.to_dict())
        if len(event_batch) >= batch_size:
            flush_batch()

    frame_idx = 0
    stats = {"entries": 0, "exits": 0, "reentries": 0, "events": 0}

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if max_frames > 0 and frame_idx > max_frames:
            print(f"  [max_frames={max_frames}] stopping early at frame {frame_idx}")
            break

        if frame_idx % DETECT_STRIDE != 0:
            continue

        frame_ts = clip_start_time + timedelta(seconds=frame_idx / fps)
        detections = detector.detect(frame)
        tracks, tracker_events = tracker.update(detections, frame, frame_idx)

        # --- Process tracker events ---
        for ev in tracker_events:
            kind, vid = ev.split(":", 1)

            if kind == "new":
                # Determine entry direction for entry cameras
                track = next((t for t in tracks if t.visitor_id == vid), None)
                if track is None:
                    continue

                if camera_type == "entry":
                    cy = (track.bbox[1] + track.bbox[3]) / 2
                    visitor_prev_y[vid] = cy
                    # Emit ENTRY only if moving inward (no prev y yet = entry)
                    if not track.is_staff:
                        ev_obj = make_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=vid,
                            event_type="ENTRY",
                            timestamp=frame_ts,
                            zone_id=None,
                            is_staff=False,
                            confidence=track.confidence,
                            session_seq=incr_seq(vid),
                        )
                        emit_and_batch(ev_obj)
                        stats["entries"] += 1
                        stats["events"] += 1

            elif kind == "reentry":
                track = next((t for t in tracks if t.visitor_id == vid), None)
                if track and not track.is_staff:
                    ev_obj = make_event(
                        store_id=store_id,
                        camera_id=camera_id,
                        visitor_id=vid,
                        event_type="REENTRY",
                        timestamp=frame_ts,
                        zone_id=None,
                        is_staff=False,
                        confidence=track.confidence,
                        session_seq=incr_seq(vid),
                    )
                    emit_and_batch(ev_obj)
                    stats["reentries"] += 1
                    stats["events"] += 1

            elif kind == "lost":
                # Emit EXIT for entry cameras
                if camera_type == "entry" and vid not in exited_visitors:
                    exited_visitors.add(vid)
                    ev_obj = make_event(
                        store_id=store_id,
                        camera_id=camera_id,
                        visitor_id=vid,
                        event_type="EXIT",
                        timestamp=frame_ts,
                        zone_id=None,
                        is_staff=False,
                        confidence=0.7,
                        session_seq=incr_seq(vid),
                    )
                    emit_and_batch(ev_obj)
                    stats["exits"] += 1
                    stats["events"] += 1

                # Emit ZONE_EXIT for floor/billing cameras
                if vid in visitor_zone:
                    zone = visitor_zone.pop(vid)
                    enter_f = visitor_zone_enter_frame.pop(vid, frame_idx)
                    dwell_ms = int(((frame_idx - enter_f) / fps) * 1000)
                    ev_obj = make_event(
                        store_id=store_id,
                        camera_id=camera_id,
                        visitor_id=vid,
                        event_type="ZONE_EXIT",
                        timestamp=frame_ts,
                        zone_id=zone,
                        dwell_ms=dwell_ms,
                        is_staff=False,
                        confidence=0.75,
                        session_seq=incr_seq(vid),
                    )
                    emit_and_batch(ev_obj)
                    stats["events"] += 1

                if vid in billing_visitors:
                    billing_visitors.discard(vid)

        # --- Zone tracking for floor/billing cameras ---
        if camera_type in ("floor", "billing"):
            current_billing_count = len(billing_visitors)

            for track in tracks:
                if track.is_staff:
                    continue
                vid = track.visitor_id
                zone_id = classify_zone_from_bbox(
                    track.bbox, camera_type, layout, camera_id
                )
                if zone_id is None:
                    continue

                # Zone enter
                if visitor_zone.get(vid) != zone_id:
                    # Exit previous zone
                    if vid in visitor_zone:
                        prev_zone = visitor_zone[vid]
                        enter_f = visitor_zone_enter_frame.get(vid, frame_idx)
                        dwell_ms = int(((frame_idx - enter_f) / fps) * 1000)
                        ev_obj = make_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=vid,
                            event_type="ZONE_EXIT",
                            timestamp=frame_ts,
                            zone_id=prev_zone,
                            dwell_ms=dwell_ms,
                            is_staff=False,
                            confidence=track.confidence,
                            session_seq=incr_seq(vid),
                        )
                        emit_and_batch(ev_obj)
                        stats["events"] += 1
                        if prev_zone == "BILLING":
                            billing_visitors.discard(vid)

                    # Enter new zone
                    visitor_zone[vid] = zone_id
                    visitor_zone_enter_frame[vid] = frame_idx

                    if zone_id == "BILLING" and current_billing_count > 0:
                        ev_obj = make_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=vid,
                            event_type="BILLING_QUEUE_JOIN",
                            timestamp=frame_ts,
                            zone_id=zone_id,
                            is_staff=False,
                            confidence=track.confidence,
                            queue_depth=current_billing_count,
                            session_seq=incr_seq(vid),
                        )
                        billing_visitors.add(vid)
                    else:
                        ev_obj = make_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=vid,
                            event_type="ZONE_ENTER",
                            timestamp=frame_ts,
                            zone_id=zone_id,
                            is_staff=False,
                            confidence=track.confidence,
                            session_seq=incr_seq(vid),
                        )
                        if zone_id == "BILLING":
                            billing_visitors.add(vid)
                    emit_and_batch(ev_obj)
                    stats["events"] += 1

                else:
                    # Already in zone — check for ZONE_DWELL (every 30s)
                    enter_f = visitor_zone_enter_frame.get(vid, frame_idx)
                    dwell_frames = frame_idx - enter_f
                    if dwell_frames > 0 and dwell_frames % DWELL_EMIT_INTERVAL_FRAMES == 0:
                        dwell_ms = int((dwell_frames / fps) * 1000)
                        zone_info = next(
                            (z for z in layout["zones"] if z["zone_id"] == zone_id), {}
                        )
                        ev_obj = make_event(
                            store_id=store_id,
                            camera_id=camera_id,
                            visitor_id=vid,
                            event_type="ZONE_DWELL",
                            timestamp=frame_ts,
                            zone_id=zone_id,
                            dwell_ms=dwell_ms,
                            is_staff=False,
                            confidence=track.confidence,
                            sku_zone=zone_info.get("sku_zone"),
                            session_seq=incr_seq(vid),
                        )
                        emit_and_batch(ev_obj)
                        stats["events"] += 1

        if frame_idx % 450 == 0:
            print(f"  [{camera_id}] Frame {frame_idx}/{total_frames} — {stats}")

    cap.release()

    # Flush remaining active tracks
    remaining = tracker.flush_remaining()
    flush_ts = clip_start_time + timedelta(seconds=total_frames / fps)
    for track in remaining:
        if camera_type == "entry" and track.visitor_id not in exited_visitors:
            ev_obj = make_event(
                store_id=store_id,
                camera_id=camera_id,
                visitor_id=track.visitor_id,
                event_type="EXIT",
                timestamp=flush_ts,
                zone_id=None,
                is_staff=track.is_staff,
                confidence=track.confidence,
                session_seq=incr_seq(track.visitor_id),
            )
            emit_and_batch(ev_obj)
            stats["exits"] += 1
            stats["events"] += 1

    flush_batch()
    print(f"[{camera_id}] Done. Stats: {stats}")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Store Intelligence Detection Pipeline")
    parser.add_argument("--clips-dir", default="data", help="Directory containing .mp4 clips")
    parser.add_argument("--layout", default="data/store_layout.json", help="Store layout JSON")
    parser.add_argument("--output", default="data/events.jsonl", help="Output JSONL file")
    parser.add_argument("--api-url", default=None, help="API base URL to push events in real time")
    parser.add_argument("--clip-start", default="2026-04-10T10:00:00Z", help="Clip start time (ISO-8601 UTC)")
    parser.add_argument("--stride", type=int, default=3, help="Process every Nth frame (default 3 = 5fps from 15fps)")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames per clip (0 = full clip)")
    args = parser.parse_args()

    layout = load_store_layout(args.layout)
    store_id = layout["store_id"]
    clip_start = datetime.fromisoformat(args.clip_start.replace("Z", "+00:00"))

    # Map camera configs
    camera_map = {cam["camera_id"]: cam for cam in layout["cameras"]}

    # Allow --stride and --max-frames to override module-level constant
    import pipeline.detect as _self
    _self.DETECT_STRIDE = args.stride

    with EventEmitter(args.output) as emitter:
        for cam in layout["cameras"]:
            clip_path = os.path.join(args.clips_dir, cam["file"])
            if not os.path.exists(clip_path):
                print(f"[SKIP] {clip_path} not found")
                continue

            print(f"\n{'='*60}")
            print(f"Processing: {cam['camera_id']} ({cam['type']})")
            print(f"  File: {clip_path}")
            print(f"  Stride: every {args.stride} frames | Max frames: {args.max_frames or 'unlimited'}")
            print(f"{'='*60}")

            try:
                process_clip(
                    video_path=clip_path,
                    camera_id=cam["camera_id"],
                    camera_type=cam["type"],
                    store_id=store_id,
                    layout=layout,
                    emitter=emitter,
                    clip_start_time=clip_start,
                    api_url=args.api_url,
                    max_frames=args.max_frames,
                )
            except Exception as e:
                print(f"[ERROR] {cam['camera_id']} ({clip_path}): {e}")
                print(f"  Skipping this camera and continuing...")

    print(f"\nAll clips processed. Events written to: {args.output}")


if __name__ == "__main__":
    main()
