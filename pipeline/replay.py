"""
Simulated real-time event replay script.
Replays a JSONL events file into the API as if events are happening live.

Usage:
  python -m pipeline.replay --file data/events.jsonl --api-url http://localhost:8000
  python -m pipeline.replay --file data/events.jsonl --api-url http://localhost:8000 --speed 10

Speed multiplier: 10 = replay 10x faster than real time.
"""

import argparse
import json
import time
import uuid
import httpx
from datetime import datetime, timezone, timedelta


def shift_to_today(events: list) -> list:
    """Shift all event timestamps so they fall on today's date."""
    today = datetime.now(timezone.utc).date()
    shifted = []
    for e in events:
        ts_str = e.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            new_ts = ts.replace(year=today.year, month=today.month, day=today.day)
            e = dict(e)
            e["timestamp"] = new_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
        shifted.append(e)
    return shifted


def replay(file_path: str, api_url: str, speed: float = 1.0, batch_size: int = 10):
    with open(file_path) as f:
        events = [json.loads(l) for l in f if l.strip()]

    if not events:
        print("No events found in file.")
        return

    # Sort events by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))

    # Shift timestamps to today so metrics queries (filtered by today's date) pick them up
    events = shift_to_today(events)

    # Regenerate event_ids so re-runs aren't blocked by the UNIQUE constraint
    for e in events:
        e["event_id"] = str(uuid.uuid4())

    print(f"Replaying {len(events)} events at {speed}x speed → {api_url}")
    print("Watch the dashboard at http://localhost:8000\n")

    sent = 0

    # Process events in batches, sleeping based on timestamp gap between batches
    batches = [events[i:i + batch_size] for i in range(0, len(events), batch_size)]
    prev_ts = None

    for batch in batches:
        # Use timestamp of first event in batch for pacing
        ts_str = batch[0].get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            ts = None

        # Sleep to simulate real-time gap between batches
        if prev_ts and ts:
            gap = (ts - prev_ts).total_seconds()
            sleep_time = gap / speed
            if 0 < sleep_time < 5:
                time.sleep(sleep_time)

        prev_ts = ts

        for attempt in range(3):
            try:
                r = httpx.post(
                    f"{api_url}/events/ingest",
                    json={"events": batch},
                    timeout=30.0,
                    headers={"Connection": "close"},
                )
                resp = r.json()
                sent += resp.get("accepted", 0)
                dupes = resp.get("duplicate", 0)
                dupe_str = f" ({dupes} dupes)" if dupes else ""
                print(f"\r  Sent {sent}/{len(events)} events{dupe_str} | {ts_str[:19]}", end="", flush=True)
                time.sleep(0.3)  # small gap to avoid overwhelming Railway
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.5)
                else:
                    print(f"\n  [ERROR] {e}")

    print(f"\n\nDone! {sent} events ingested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay events into the API in simulated real-time")
    parser.add_argument("--file", default="data/events.jsonl", help="Path to JSONL events file")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--speed", type=float, default=10.0, help="Replay speed multiplier (default 10x)")
    args = parser.parse_args()
    replay(args.file, args.api_url, args.speed)
