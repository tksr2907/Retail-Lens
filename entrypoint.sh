#!/usr/bin/env bash
# ============================================================
# RetailLens — Detection Pipeline Entrypoint
#
# Usage (docker compose):
#   docker compose up               → API only (seeded data)
#   docker compose --profile pipeline up   → API + real YOLO pipeline
#
# Usage (manual):
#   CLIPS_DIR=data API_URL=http://localhost:8000 bash entrypoint.sh
# ============================================================
set -e

CLIPS_DIR="${CLIPS_DIR:-/app/data}"
LAYOUT="${LAYOUT:-/app/data/store_layout.json}"
OUTPUT="${OUTPUT:-/app/data/events.jsonl}"
API_URL="${API_URL:-http://api:8000}"
STRIDE="${DETECT_STRIDE:-3}"        # process every Nth frame (3 = 5fps from 15fps)
MAX_FRAMES="${MAX_FRAMES:-0}"       # 0 = entire clip; set e.g. 450 for first 30s

echo "========================================================"
echo "  RetailLens Detection Pipeline"
echo "========================================================"
echo "  Clips dir  : $CLIPS_DIR"
echo "  Layout     : $LAYOUT"
echo "  Output     : $OUTPUT"
echo "  API URL    : $API_URL"
echo "  Stride     : every ${STRIDE} frames"
echo "  Max frames : ${MAX_FRAMES:-unlimited}"
echo "========================================================"

# Wait for the API to be healthy before pushing events
wait_for_api() {
    echo "Waiting for API at $API_URL ..."
    for i in $(seq 1 30); do
        if curl -sf "$API_URL/health" > /dev/null 2>&1; then
            echo "API is ready."
            return 0
        fi
        sleep 2
    done
    echo "ERROR: API did not become ready in 60 seconds."
    exit 1
}

wait_for_api

# Check if any video files are present
VIDEO_COUNT=$(find "$CLIPS_DIR" -maxdepth 1 -name "*.mp4" 2>/dev/null | wc -l)

if [ "$VIDEO_COUNT" -eq 0 ]; then
    echo "No .mp4 files found in $CLIPS_DIR — skipping detection."
    echo "To run detection, place CAM 1.mp4 ... CAM 5.mp4 in the data/ directory."
    exit 0
fi

echo "Found $VIDEO_COUNT video file(s). Starting YOLO detection..."

# Run the detection pipeline
python3 -m pipeline.detect \
    --clips-dir "$CLIPS_DIR" \
    --layout "$LAYOUT" \
    --output "$OUTPUT" \
    --api-url "$API_URL" \
    --stride "$STRIDE" \
    ${MAX_FRAMES:+--max-frames "$MAX_FRAMES"}

echo ""
echo "Detection complete. Events written to: $OUTPUT"
echo ""

# Push any remaining buffered events
if [ -f "$OUTPUT" ]; then
    TOTAL=$(wc -l < "$OUTPUT")
    echo "Pushing $TOTAL events to API..."
    python3 -c "
import json, httpx, sys

with open('$OUTPUT') as f:
    lines = [json.loads(l) for l in f if l.strip()]

batch_size = 200
pushed = 0
for i in range(0, len(lines), batch_size):
    batch = lines[i:i+batch_size]
    try:
        r = httpx.post('$API_URL/events/ingest', json={'events': batch}, timeout=30)
        result = r.json()
        pushed += result.get('accepted', 0)
        print(f'  Batch {i//batch_size+1}: accepted={result.get(\"accepted\",0)} dup={result.get(\"duplicate\",0)}')
    except Exception as e:
        print(f'  Batch {i//batch_size+1} error: {e}')

print(f'Total pushed: {pushed}/{len(lines)} events')
"
fi

echo ""
echo "Pipeline complete. Check metrics at: $API_URL/metrics"
