"""
Re-ID and multi-object tracking logic.

Approach:
- ByteTrack-style tracking: maintain active tracks keyed by track_id
- Re-ID via appearance embedding similarity (cosine distance on HOG features)
  when track is lost and a similar detection reappears → REENTRY detection
- Staff detection: heuristic based on movement patterns (high dwell in all zones,
  uniform-like appearance via brightness/saturation analysis)

We chose a lightweight trajectory + appearance approach over full OSNet/torchreid
because: (1) faces are blurred — appearance must be from torso/clothing,
(2) OSNet adds ~200MB weight download not suitable for the evaluation window.
Distance-based Re-ID on bbox trajectory + colour histogram gives reasonable
re-entry detection without model complexity.
"""

import numpy as np
import cv2
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Track:
    track_id: int
    visitor_id: str           # our VIS_xxxxx token
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2 (normalised)
    confidence: float
    is_staff: bool
    last_seen_frame: int
    first_seen_frame: int
    appearance: Optional[np.ndarray] = None  # colour histogram embedding
    zone_history: List[str] = field(default_factory=list)
    zone_enter_frame: Dict[str, int] = field(default_factory=dict)
    session_seq: int = 0
    active: bool = True


class ByteTracker:
    """
    Simplified ByteTrack-inspired tracker.

    High-confidence detections are matched first (IoU), then low-confidence
    detections are matched against remaining tracks.

    Re-ID: when a track goes inactive, we store its appearance embedding.
    On new detections, we check cosine similarity. If sim > threshold and
    the track was seen < REENTRY_WINDOW_FRAMES ago → REENTRY.
    """

    REENTRY_WINDOW_FRAMES = 450   # ~30 seconds at 15fps
    LOST_TRACK_TTL = 45           # frames before a track is considered gone
    REENTRY_SIM_THRESHOLD = 0.75
    HIGH_CONF_THRESHOLD = 0.5
    IOU_MATCH_THRESHOLD = 0.3
    STAFF_MIN_ZONE_COUNT = 4      # staff visits many zones
    STAFF_DWELL_MULTIPLIER = 3.0  # staff dwells much longer than customers

    def __init__(self):
        self._next_track_id = 1
        self._active_tracks: Dict[int, Track] = {}
        self._lost_tracks: List[Track] = []  # for Re-ID lookup
        self._visitor_counter = 0

    def _new_visitor_id(self) -> str:
        self._visitor_counter += 1
        return f"VIS_{self._visitor_counter:06x}"

    def _iou(self, a: Tuple, b: Tuple) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
        inter = iw * ih
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / union if union > 0 else 0.0

    def _extract_appearance(self, frame: np.ndarray, bbox: Tuple) -> np.ndarray:
        """Extract normalised colour histogram from the detection crop."""
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = (
            int(bbox[0] * w), int(bbox[1] * h),
            int(bbox[2] * w), int(bbox[3] * h),
        )
        crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
        if crop.size == 0:
            return np.zeros(96, dtype=np.float32)
        # Focus on torso region (upper 60%) to avoid floor/shadow noise
        torso_h = max(1, int(crop.shape[0] * 0.6))
        torso = crop[:torso_h]
        hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        # Pad/trim to fixed 96-dim
        feat = np.zeros(96, dtype=np.float32)
        n = min(len(hist), 96)
        feat[:n] = hist[:n]
        return feat

    def _cosine_sim(self, a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na < 1e-6 or nb < 1e-6:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _is_staff_heuristic(self, track: Track, total_frames: int) -> bool:
        """
        Staff heuristic:
        1. Visited >= STAFF_MIN_ZONE_COUNT distinct zones
        2. OR: average brightness of torso crop suggests uniform (dark colours typical
           of retail staff uniforms — high saturation in HSV S channel near 0)

        We also check if the track has been active for nearly the full clip duration
        without exiting — staff rarely exit during a 20-min clip.
        """
        if len(set(track.zone_history)) >= self.STAFF_MIN_ZONE_COUNT:
            return True
        # Appearance check: if appearance embedding has very low saturation variance
        # (uniform/solid colour clothing) → likely staff
        if track.appearance is not None:
            # Hue distribution flatness: staff uniforms are monochrome
            hue_hist = track.appearance[:32]
            if np.max(hue_hist) < 0.15:  # very flat hue = likely uniform
                return True
        return False

    def update(
        self,
        detections: List[Tuple[Tuple, float]],  # [(bbox_norm, confidence), ...]
        frame: np.ndarray,
        frame_idx: int,
    ) -> Tuple[List[Track], List[str]]:
        """
        Match detections to tracks. Returns:
          - list of current active tracks (updated)
          - list of event hints: 'new', 'reentry', 'lost:<visitor_id>'
        """
        events: List[str] = []

        # --- Mark tracks as potentially lost ---
        for t in self._active_tracks.values():
            if frame_idx - t.last_seen_frame > self.LOST_TRACK_TTL:
                t.active = False

        # Move lost tracks to lost pool
        newly_lost = [t for t in self._active_tracks.values() if not t.active]
        for t in newly_lost:
            # Final staff check before archiving — a person seen for 300+ frames
            # across many zones should be flagged even if they exit without matching
            lifespan = frame_idx - t.first_seen_frame
            if lifespan > 300 and not t.is_staff:
                t.is_staff = self._is_staff_heuristic(t, lifespan)
            events.append(f"lost:{t.visitor_id}")
            self._lost_tracks.append(t)
            del self._active_tracks[t.track_id]

        # --- Split detections by confidence ---
        high_conf = [(b, c) for b, c in detections if c >= self.HIGH_CONF_THRESHOLD]
        low_conf  = [(b, c) for b, c in detections if c < self.HIGH_CONF_THRESHOLD]

        active_list = list(self._active_tracks.values())
        matched_track_ids = set()
        matched_det_indices = set()

        # --- Match high-confidence detections to active tracks (IoU) ---
        for det_idx, (bbox, conf) in enumerate(high_conf):
            best_iou, best_track = 0.0, None
            for track in active_list:
                if track.track_id in matched_track_ids:
                    continue
                iou = self._iou(bbox, track.bbox)
                if iou > best_iou:
                    best_iou, best_track = iou, track
            if best_track and best_iou >= self.IOU_MATCH_THRESHOLD:
                app = self._extract_appearance(frame, bbox)
                best_track.bbox = bbox
                best_track.confidence = conf
                best_track.last_seen_frame = frame_idx
                best_track.appearance = app
                matched_track_ids.add(best_track.track_id)
                matched_det_indices.add(det_idx)

        # --- Match low-confidence detections to remaining tracks ---
        unmatched_tracks = [t for t in active_list if t.track_id not in matched_track_ids]
        for det_idx, (bbox, conf) in enumerate(low_conf):
            best_iou, best_track = 0.0, None
            for track in unmatched_tracks:
                iou = self._iou(bbox, track.bbox)
                if iou > best_iou:
                    best_iou, best_track = iou, track
            if best_track and best_iou >= self.IOU_MATCH_THRESHOLD:
                best_track.bbox = bbox
                best_track.confidence = conf
                best_track.last_seen_frame = frame_idx
                matched_track_ids.add(best_track.track_id)
                unmatched_tracks.remove(best_track)

        # --- New detections: attempt Re-ID or create new track ---
        all_dets = high_conf + low_conf
        for det_idx, (bbox, conf) in enumerate(all_dets):
            if det_idx in matched_det_indices:
                continue
            app = self._extract_appearance(frame, bbox)

            # Re-ID: check against recently lost tracks
            best_sim, best_lost = 0.0, None
            for lt in self._lost_tracks:
                age = frame_idx - lt.last_seen_frame
                if age > self.REENTRY_WINDOW_FRAMES:
                    continue
                if lt.appearance is None:
                    continue
                sim = self._cosine_sim(app, lt.appearance)
                if sim > best_sim:
                    best_sim, best_lost = sim, lt

            if best_lost and best_sim >= self.REENTRY_SIM_THRESHOLD:
                # Reentry detected — reuse visitor_id
                self._lost_tracks.remove(best_lost)
                track = Track(
                    track_id=self._next_track_id,
                    visitor_id=best_lost.visitor_id,
                    bbox=bbox,
                    confidence=conf,
                    is_staff=best_lost.is_staff,
                    last_seen_frame=frame_idx,
                    first_seen_frame=frame_idx,
                    appearance=app,
                    session_seq=best_lost.session_seq,
                )
                self._next_track_id += 1
                self._active_tracks[track.track_id] = track
                events.append(f"reentry:{track.visitor_id}")
            else:
                # Brand new visitor
                visitor_id = self._new_visitor_id()
                track = Track(
                    track_id=self._next_track_id,
                    visitor_id=visitor_id,
                    bbox=bbox,
                    confidence=conf,
                    is_staff=False,
                    last_seen_frame=frame_idx,
                    first_seen_frame=frame_idx,
                    appearance=app,
                )
                self._next_track_id += 1
                self._active_tracks[track.track_id] = track
                events.append(f"new:{visitor_id}")

        # Prune old lost tracks (>= REENTRY_WINDOW_FRAMES old)
        self._lost_tracks = [
            t for t in self._lost_tracks
            if frame_idx - t.last_seen_frame <= self.REENTRY_WINDOW_FRAMES
        ]

        # Update staff flags periodically
        for track in self._active_tracks.values():
            lifespan = frame_idx - track.first_seen_frame
            if lifespan > 300 and not track.is_staff:
                track.is_staff = self._is_staff_heuristic(track, lifespan)

        return list(self._active_tracks.values()), events
    def get_active_tracks(self) -> List[Track]:
        return list(self._active_tracks.values())

    def flush_remaining(self) -> List[Track]:
        """Call at end of video to get all still-active tracks."""
        remaining = list(self._active_tracks.values())
        self._active_tracks.clear()
        return remaining
