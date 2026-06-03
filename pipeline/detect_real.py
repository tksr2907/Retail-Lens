"""
Real video detection pipeline using OpenCV MOG2 background subtraction.

This runs YOLO if available (ultralytics + torch), otherwise falls back to
OpenCV MOG2 + contour tracking — a legitimate production approach used when
GPU/torch is unavailable or for edge-device deployment.

Usage:
  python -m pipeline.detect_real --store STORE_BLR_002
  python -m pipeline.detect_real --store STORE_BLR_001
  python -m pipeline.detect_real  # processes both stores

# PROMPT (Claude, 2026): "Implement person detection and tracking from CCTV
# video without GPU. Use OpenCV background subtraction + contour tracking with
# IOU-based track assignment. Handle entry/exit via virtual tripwire, zone
# classification via bbox centroid, staff heuristics via long dwell time."
# CHANGES MADE: Added HSV colour histogram Re-ID, billing queue depth tracking,
# proper event schema compliance, timestamp derivation from clip start + frame offset.
"""

import cv2
import json
import uuid
import os
import sys
import argparse
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Try YOLO first
try:
    from ultralytics import YOLO
    import torch
    YOLO_AVAILABLE = True
    print("YOLO available — using YOLOv8n for detection")
except ImportError:
    YOLO_AVAILABLE = False
    print("YOLO/torch not available — using OpenCV MOG2 background subtraction")

DATA_DIR = Path(__file__).parent.parent / "data"
DETECT_STRIDE = 3       # process every 3rd frame (5 fps effective from 15fps)
DWELL_EMIT_FRAMES = 450 # ~30s at 15fps; adjusted per actual fps
MIN_PERSON_AREA = 2500  # min contour area (px²) to count as a person
MAX_PERSON_AREA = 120000
MIN_ASPECT = 0.25       # width/height ratio range for person bounding box
MAX_ASPECT = 1.2
IOU_THRESHOLD = 0.2     # IoU for track matching
TRACK_LOST_FRAMES = 60  # frames before a track is considered lost
REENTRY_WINDOW = 900    # frames: lost track eligible for reentry match
STAFF_ZONE_THRESHOLD = 4  # zones visited → staff heuristic
STAFF_TIME_THRESHOLD = 300  # seconds continuously present → staff


# ── Track ────────────────────────────────────────────────────────────────────
class Track:
    def __init__(self, track_id: str, bbox: Tuple, frame: int, store_id: str):
        self.track_id = track_id
        self.visitor_id = f"VIS_{uuid.uuid4().hex[:6].upper()}"
        self.bboxes: List[Tuple] = [bbox]
        self.frames: List[int] = [frame]
        self.last_frame = frame
        self.lost_since: Optional[int] = None
        self.is_active = True
        self.is_staff = False
        self.zones_visited: List[str] = []
        self.current_zone: Optional[str] = None
        self.zone_enter_frame: Optional[int] = None
        self.dwell_emit_frame: Optional[int] = None
        self.session_seq = 0
        self.crossed_entry = False   # has entered store
        self.has_exited = False
        self.entry_side: Optional[str] = None  # 'in' or 'out'
        self.hist: Optional[np.ndarray] = None  # colour histogram for Re-ID
        self.store_id = store_id
        self.entry_frame: Optional[int] = None

    @property
    def bbox(self) -> Tuple:
        return self.bboxes[-1]

    @property
    def center(self) -> Tuple[float, float]:
        x, y, w, h = self.bbox
        return x + w/2, y + h/2

    def update(self, bbox: Tuple, frame: int):
        self.bboxes.append(bbox)
        self.frames.append(frame)
        self.last_frame = frame
        self.lost_since = None
        self.is_active = True

    def next_seq(self) -> int:
        self.session_seq += 1
        return self.session_seq


# ── Zone classifier ───────────────────────────────────────────────────────────
def classify_zone(cx_frac: float, cy_frac: float, layout: Dict, cam_type: str) -> Optional[str]:
    if cam_type == 'entry':
        return None  # entry camera only emits ENTRY/EXIT
    if cam_type == 'billing':
        return 'BILLING'
    
    for zone in layout.get('zones', []):
        if zone['zone_id'] in ('ENTRY', 'BILLING'):
            continue
        bbox = zone.get('bbox')
        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            if x1 <= cx_frac <= x2 and y1 <= cy_frac <= y2:
                return zone['zone_id']
    return None


# ── IOU ───────────────────────────────────────────────────────────────────────
def iou(b1: Tuple, b2: Tuple) -> float:
    x1,y1,w1,h1 = b1; x2,y2,w2,h2 = b2
    ix = max(0, min(x1+w1, x2+w2) - max(x1, x2))
    iy = max(0, min(y1+h1, y2+h2) - max(y1, y2))
    inter = ix * iy
    union = w1*h1 + w2*h2 - inter
    return inter / union if union > 0 else 0


# ── Colour histogram Re-ID ────────────────────────────────────────────────────
def compute_hist(frame: np.ndarray, bbox: Tuple) -> np.ndarray:
    x, y, w, h = [int(v) for v in bbox]
    # crop torso (middle third)
    ty = y + h//3; th = h//3
    crop = frame[max(0,ty):ty+th, max(0,x):x+w]
    if crop.size == 0:
        return np.zeros(96)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_hist = cv2.calcHist([hsv],[0],None,[32],[0,180]).flatten()
    s_hist = cv2.calcHist([hsv],[1],None,[32],[0,256]).flatten()
    v_hist = cv2.calcHist([hsv],[2],None,[32],[0,256]).flatten()
    hist = np.concatenate([h_hist, s_hist, v_hist])
    norm = np.linalg.norm(hist)
    return hist / norm if norm > 0 else hist


def hist_similarity(h1: np.ndarray, h2: np.ndarray) -> float:
    if h1 is None or h2 is None or h1.shape != h2.shape:
        return 0.0
    return float(np.dot(h1, h2))


# ── MOG2 person detector ──────────────────────────────────────────────────────
class MOG2Detector:
    def __init__(self):
        self.bg = cv2.createBackgroundSubtractorMOG2(
            history=200, varThreshold=40, detectShadows=False)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def detect(self, frame: np.ndarray) -> List[Tuple]:
        """Returns list of (x,y,w,h) bboxes of detected people."""
        fg = self.bg.apply(frame)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN,  self.kernel, iterations=1)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, self.kernel, iterations=3)
        fg = cv2.dilate(fg, self.kernel, iterations=2)
        cnts, _ = cv2.findContours(fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detections = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < MIN_PERSON_AREA or area > MAX_PERSON_AREA:
                continue
            x, y, w, h = cv2.boundingRect(c)
            ratio = w / h if h > 0 else 0
            if not (MIN_ASPECT <= ratio <= MAX_ASPECT):
                continue
            detections.append((x, y, w, h))
        return self._merge_overlapping(detections)

    def _merge_overlapping(self, dets):
        if not dets: return dets
        merged = True
        while merged:
            merged = False
            result = []
            used = set()
            for i, d1 in enumerate(dets):
                if i in used: continue
                group = [d1]
                for j, d2 in enumerate(dets):
                    if j <= i or j in used: continue
                    if iou(d1, d2) > 0.3:
                        group.append(d2); used.add(j); merged = True
                used.add(i)
                if len(group) == 1:
                    result.append(group[0])
                else:
                    xs = [g[0] for g in group]; ys = [g[1] for g in group]
                    x2s = [g[0]+g[2] for g in group]; y2s = [g[1]+g[3] for g in group]
                    result.append((min(xs),min(ys),max(x2s)-min(xs),max(y2s)-min(ys)))
            dets = result
        return dets


# ── YOLO detector wrapper ──────────────────────────────────────────────────────
class YOLODetector:
    def __init__(self):
        self.model = YOLO('yolov8n.pt')

    def detect(self, frame: np.ndarray) -> List[Tuple]:
        results = self.model(frame, classes=[0], verbose=False)[0]
        dets = []
        for box in results.boxes:
            x1,y1,x2,y2 = box.xyxy[0].tolist()
            dets.append((int(x1), int(y1), int(x2-x1), int(y2-y1)))
        return dets


# ── Event builder ─────────────────────────────────────────────────────────────
def make_event(store_id, camera_id, track: Track, event_type: str,
               timestamp: str, zone_id=None, dwell_ms=0,
               queue_depth=None, sku_zone=None, confidence=0.82) -> Dict:
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": camera_id,
        "visitor_id": track.visitor_id,
        "event_type": event_type,
        "timestamp": timestamp,
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": track.is_staff,
        "confidence": round(confidence, 3),
        "metadata": {
            "queue_depth": queue_depth,
            "sku_zone": sku_zone or zone_id,
            "session_seq": track.next_seq()
        }
    }


def frame_to_ts(clip_start: datetime, frame: int, fps: float) -> str:
    dt = clip_start + timedelta(seconds=frame / fps)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Main processor ────────────────────────────────────────────────────────────
def process_camera(video_path: str, camera: Dict, store_id: str,
                   layout: Dict, clip_start: datetime,
                   max_frames: int = 0) -> List[Dict]:
    """Process one camera video file → list of events."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"  ERROR: Cannot open {video_path}")
        return []

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cam_id = camera['camera_id']
    cam_type = camera['type']
    limit = min(max_frames, total_frames) if max_frames > 0 else total_frames

    print(f"  Processing {cam_id} ({cam_type}): {W}x{H}@{fps:.0f}fps, {limit}/{total_frames} frames")

    # Entry line for entry cameras
    entry_y_frac = 0.55
    for z in layout.get('zones', []):
        if z['zone_id'] == 'ENTRY':
            entry_y_frac = z.get('entry_line_y_fraction', 0.55)

    detector = YOLODetector() if YOLO_AVAILABLE else MOG2Detector()
    active_tracks: Dict[str, Track] = {}
    lost_tracks: List[Track] = []
    events: List[Dict] = []
    billing_occupants = 0
    frame_idx = 0

    # Warmup background subtractor (first 60 frames)
    if not YOLO_AVAILABLE:
        warmup = min(60, limit)
        for _ in range(warmup):
            ret, frame = cap.read()
            if ret:
                detector.detect(frame)
            frame_idx += 1
        print(f"    Background warmup done ({warmup} frames)")

    frame_idx = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while frame_idx < limit:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if frame_idx % DETECT_STRIDE != 0:
            continue

        ts = frame_to_ts(clip_start, frame_idx, fps)
        
        # Detect
        try:
            raw_dets = detector.detect(frame)
        except Exception:
            continue

        if frame_idx % 300 == 0:
            det_count = len(raw_dets)
            print(f"    Frame {frame_idx}/{limit}: {det_count} detections, {len(active_tracks)} tracks")

        # Normalise detections to fractions
        dets = [((x/W, y/H, w/W, h/H), (x,y,w,h)) for (x,y,w,h) in raw_dets]

        # Match detections to existing tracks
        matched_track_ids = set()
        matched_det_idx = set()

        for tid, track in list(active_tracks.items()):
            best_iou = IOU_THRESHOLD
            best_j = -1
            for j, (_, bbox_px) in enumerate(dets):
                if j in matched_det_idx:
                    continue
                # Convert track bbox (frac) back to px for IOU
                tx,ty,tw,th = track.bbox
                tb = (int(tx*W), int(ty*H), int(tw*W), int(th*H))
                score = iou(tb, bbox_px)
                if score > best_iou:
                    best_iou = score; best_j = j

            if best_j >= 0:
                frac_bbox, _ = dets[best_j]
                track.update(frac_bbox, frame_idx)
                matched_track_ids.add(tid)
                matched_det_idx.add(best_j)
            else:
                if track.lost_since is None:
                    track.lost_since = frame_idx
                if frame_idx - track.lost_since > TRACK_LOST_FRAMES:
                    # Emit EXIT if this track had entered
                    if track.crossed_entry and not track.has_exited:
                        events.append(make_event(
                            store_id, cam_id, track, "EXIT", ts,
                            confidence=0.75))
                        track.has_exited = True
                        if cam_type == 'billing':
                            billing_occupants = max(0, billing_occupants - 1)
                    del active_tracks[tid]
                    track.is_active = False
                    lost_tracks.append(track)

        # New detections → new or reentry tracks
        for j, (frac_bbox, px_bbox) in enumerate(dets):
            if j in matched_det_idx:
                continue

            # Compute histogram for Re-ID
            hist = compute_hist(frame, px_bbox)

            # Check reentry against lost tracks
            reentry_track = None
            best_sim = 0.72
            for lt in lost_tracks[-50:]:  # only check recent lost tracks
                if lt.has_exited and frame_idx - lt.last_frame < REENTRY_WINDOW:
                    sim = hist_similarity(hist, lt.hist)
                    if sim > best_sim:
                        best_sim = sim
                        reentry_track = lt

            if reentry_track:
                # Re-entry
                reentry_track.visitor_id = reentry_track.visitor_id  # same ID
                reentry_track.update(frac_bbox, frame_idx)
                reentry_track.is_active = True
                reentry_track.has_exited = False
                reentry_track.lost_since = None
                active_tracks[reentry_track.track_id] = reentry_track
                lost_tracks.remove(reentry_track)
                events.append(make_event(
                    store_id, cam_id, reentry_track, "REENTRY", ts,
                    confidence=round(best_sim, 3)))
            else:
                # New track
                new_id = f"T_{uuid.uuid4().hex[:8]}"
                t = Track(new_id, frac_bbox, frame_idx, store_id)
                t.hist = hist
                active_tracks[new_id] = t

                # Entry detection for entry cameras
                if cam_type == 'entry':
                    cx, cy, cw, ch = frac_bbox
                    cy_center = cy + ch/2
                    if cy_center < entry_y_frac + 0.15:
                        t.crossed_entry = True
                        t.entry_frame = frame_idx
                        events.append(make_event(
                            store_id, cam_id, t, "ENTRY", ts,
                            confidence=min(0.97, 0.80 + best_sim * 0.1)))

                # Zone enter for floor/billing cameras
                elif cam_type in ('floor', 'billing'):
                    cx_f, cy_f, cw_f, ch_f = frac_bbox
                    zone = classify_zone(cx_f + cw_f/2, cy_f + ch_f/2, layout, cam_type)
                    if zone:
                        t.current_zone = zone
                        t.zone_enter_frame = frame_idx
                        t.dwell_emit_frame = frame_idx + int(DWELL_EMIT_FRAMES * 30 / fps)
                        if zone not in t.zones_visited:
                            t.zones_visited.append(zone)
                        
                        # Staff heuristic: check if too many zones
                        if len(t.zones_visited) >= STAFF_ZONE_THRESHOLD:
                            t.is_staff = True

                        if zone == 'BILLING':
                            billing_occupants += 1
                            if billing_occupants > 1:
                                events.append(make_event(
                                    store_id, cam_id, t, "BILLING_QUEUE_JOIN", ts,
                                    zone_id=zone, queue_depth=billing_occupants,
                                    confidence=0.88))
                            else:
                                events.append(make_event(
                                    store_id, cam_id, t, "ZONE_ENTER", ts,
                                    zone_id=zone, sku_zone=zone, confidence=0.88))
                        else:
                            t.crossed_entry = True  # floor cam = in store
                            events.append(make_event(
                                store_id, cam_id, t, "ZONE_ENTER", ts,
                                zone_id=zone, sku_zone=zone, confidence=0.82))

        # Zone dwell events
        for tid, track in list(active_tracks.items()):
            if not track.is_active or track.current_zone is None:
                continue
            if track.dwell_emit_frame and frame_idx >= track.dwell_emit_frame:
                dwell_ms = int((frame_idx - track.zone_enter_frame) / fps * 1000)
                events.append(make_event(
                    store_id, cam_id, track, "ZONE_DWELL", ts,
                    zone_id=track.current_zone,
                    sku_zone=track.current_zone,
                    dwell_ms=dwell_ms, confidence=0.90))
                track.dwell_emit_frame += int(DWELL_EMIT_FRAMES * 30 / fps)

        # Zone change detection
        for tid, track in list(active_tracks.items()):
            if not track.is_active or cam_type == 'entry':
                continue
            cx, cy, cw, ch = track.bbox
            new_zone = classify_zone(cx + cw/2, cy + ch/2, layout, cam_type)
            if new_zone and new_zone != track.current_zone:
                if track.current_zone:
                    dwell_ms = int((frame_idx - (track.zone_enter_frame or frame_idx)) / fps * 1000)
                    events.append(make_event(
                        store_id, cam_id, track, "ZONE_EXIT", ts,
                        zone_id=track.current_zone,
                        sku_zone=track.current_zone,
                        dwell_ms=dwell_ms, confidence=0.80))
                    if track.current_zone == 'BILLING':
                        billing_occupants = max(0, billing_occupants - 1)
                        # Check for abandon: left billing without a POS transaction soon after
                        # (simplified: if dwell < 60s, likely abandon)
                        if dwell_ms < 60000:
                            events.append(make_event(
                                store_id, cam_id, track, "BILLING_QUEUE_ABANDON", ts,
                                zone_id='BILLING', dwell_ms=dwell_ms, confidence=0.72))
                track.current_zone = new_zone
                track.zone_enter_frame = frame_idx
                track.dwell_emit_frame = frame_idx + int(DWELL_EMIT_FRAMES * 30 / fps)
                if new_zone not in track.zones_visited:
                    track.zones_visited.append(new_zone)
                if len(track.zones_visited) >= STAFF_ZONE_THRESHOLD:
                    track.is_staff = True
                events.append(make_event(
                    store_id, cam_id, track, "ZONE_ENTER", ts,
                    zone_id=new_zone, sku_zone=new_zone, confidence=0.82))

    # Emit EXIT for all still-active entry tracks
    for track in active_tracks.values():
        if cam_type == 'entry' and track.crossed_entry and not track.has_exited:
            ts = frame_to_ts(clip_start, frame_idx, fps)
            events.append(make_event(store_id, cam_id, track, "EXIT", ts, confidence=0.70))

    cap.release()
    print(f"    Done: {len(events)} events from {frame_idx} frames")
    return events


def process_store(store_id: str, layout_path: str, data_dir: Path,
                  output_path: str, max_frames: int = 0,
                  clip_start: Optional[datetime] = None):
    """Process all cameras for a store."""
    if clip_start is None:
        # Anchor to today 10am
        now = datetime.now(timezone.utc)
        clip_start = now.replace(hour=10, minute=0, second=0, microsecond=0)

    with open(layout_path) as f:
        layout = json.load(f)

    cameras = layout.get('cameras', [])
    print(f"\n{'='*60}")
    print(f"Processing {store_id} ({layout.get('store_name','')}) — {len(cameras)} cameras")
    print(f"Clip start: {clip_start}")
    print(f"{'='*60}")

    all_events = []
    cam_start = clip_start

    for camera in cameras:
        video_file = camera.get('file', '')
        video_path = str(data_dir / video_file)
        if not os.path.exists(video_path):
            print(f"  SKIP {camera['camera_id']}: {video_path} not found")
            continue

        cam_events = process_camera(
            video_path, camera, store_id, layout,
            cam_start, max_frames=max_frames)
        all_events.extend(cam_events)
        
        # Each camera clip starts slightly after the previous
        cap = cv2.VideoCapture(video_path)
        dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 25)
        cap.release()
        cam_start = clip_start  # all cameras run concurrently

    # Sort by timestamp
    all_events.sort(key=lambda e: e['timestamp'])

    # Write output
    with open(output_path, 'w') as f:
        for ev in all_events:
            f.write(json.dumps(ev) + '\n')

    # Stats
    event_types = defaultdict(int)
    for ev in all_events:
        event_types[ev['event_type']] += 1
    entries = event_types.get('ENTRY', 0)
    exits = event_types.get('EXIT', 0)
    zone_enters = event_types.get('ZONE_ENTER', 0)
    print(f"\n{store_id} Summary:")
    print(f"  Total events: {len(all_events)}")
    print(f"  Event types: {dict(event_types)}")
    print(f"  Entry/Exit balance: {entries} in / {exits} out")
    print(f"  Output: {output_path}")
    return all_events


def main():
    parser = argparse.ArgumentParser(description='RetailLens real video detection')
    parser.add_argument('--store', default='both', choices=['STORE_BLR_002','STORE_BLR_001','both'])
    parser.add_argument('--max-frames', type=int, default=0, help='0=all frames')
    parser.add_argument('--output-dir', default=str(DATA_DIR))
    args = parser.parse_args()

    data_dir = DATA_DIR
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    today_10am = now.replace(hour=10, minute=0, second=0, microsecond=0)

    stores = []
    if args.store in ('STORE_BLR_002', 'both'):
        stores.append(('STORE_BLR_002', str(data_dir / 'store_layout.json'),
                        str(output_dir / 'events_store1.jsonl')))
    if args.store in ('STORE_BLR_001', 'both'):
        stores.append(('STORE_BLR_001', str(data_dir / 'store2_layout.json'),
                        str(output_dir / 'events_store2.jsonl')))

    all_events = []
    for store_id, layout_path, output_path in stores:
        events = process_store(store_id, layout_path, data_dir, output_path,
                               max_frames=args.max_frames,
                               clip_start=today_10am)
        all_events.extend(events)

    # Merge into sample_events.jsonl
    all_events.sort(key=lambda e: e['timestamp'])
    merged_path = str(output_dir / 'sample_events.jsonl')
    with open(merged_path, 'w') as f:
        for ev in all_events:
            f.write(json.dumps(ev) + '\n')
    print(f"\nMerged output: {merged_path} ({len(all_events)} events total)")


if __name__ == '__main__':
    main()
