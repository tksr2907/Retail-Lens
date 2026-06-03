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
import httpx
from datetime import datetime, timezone


def replay(file_path: str, api_url: str, speed: float = 1.0, batch_size: int = 10):
    with open(file_path) as f:
        events = [json.loads(l) for l in f if l.strip()]

    if not events:
        print("No events found in file.")
        return

    print(f"Replaying {len(events)} events at {speed}x speed → {api_url}")
    print("Watch the dashboard at http://localhost:8000\n")

    # Sort events by timestamp
    events.sort(key=lambda e: e.get("timestamp", ""))

    sent = 0
    prev_ts = None

    for i, event in enumerate(events):
        ts_str = event.get("timestamp", "")
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            ts = None

        # Sleep to simulate real-time gap between events
        if prev_ts and ts:
            gap = (ts - prev_ts).total_seconds()
            sleep_time = gap / speed
            if 0 < sleep_time < 5:
                time.sleep(sleep_time)

        prev_ts = ts

        # Send in small batches
        batch = events[i:i + batch_size]
        try:
            r = httpx.post(
                f"{api_url}/events/ingest",
                json={"events": batch},
                timeout=10.0,
            )
            sent += r.json().get("accepted", 0)
            print(f"\r  Sent {sent}/{len(events)} events | {ts_str[:19]}", end="", flush=True)
        except Exception as e:
            print(f"\n  [ERROR] {e}")

    print(f"\n\nDone! {sent} events ingested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay events into the API in simulated real-time")
    parser.add_argument("--file", default="data/events.jsonl", help="Path to JSONL events file")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--speed", type=float, default=10.0, help="Replay speed multiplier (default 10x)")
    args = parser.parse_args()
    replay(args.file, args.api_url, args.speed)
