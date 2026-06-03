#!/usr/bin/env bash
# One command to process all CCTV clips and feed events into the API.
#
# Usage:
#   bash pipeline/run.sh                                    # batch mode only
#   bash pipeline/run.sh --api-url http://localhost:8000    # push to API in real time
#   CLIPS_DIR="Store 1/Store 1" bash pipeline/run.sh       # specific store folder
#   MAX_FRAMES=450 bash pipeline/run.sh                     # first 30s per clip (fast test)
#
# Store 1 video files: CAM 1 - zone.mp4, CAM 2 - zone.mp4, CAM 3 - entry.mp4, CAM 5 - billing.mp4
# Store 2 video files: entry 1.mp4, entry 2.mp4, zone.mp4, billing_area.mp4

set -e

# ── Configuration ─────────────────────────────────────────────────────────────
CLIPS_DIR="${CLIPS_DIR:-Store 1-20260602T101818Z-3-001ec38db8/Store 1}"
LAYOUT="${LAYOUT:-data/store_layout.json}"
OUTPUT="${OUTPUT:-data/events.jsonl}"
API_URL="${API_URL:-}"
MAX_FRAMES="${MAX_FRAMES:-0}"
STRIDE="${DETECT_STRIDE:-3}"
CLIP_START="${CLIP_START:-2026-04-10T10:00:00Z}"

# Parse --api-url argument
for i in "$@"; do
  case $i in
    --api-url=*) API_URL="${i#*=}" ;;
    --api-url) API_URL="$2"; shift ;;
  esac
done

echo "=========================================="
echo "  Store Intelligence Detection Pipeline"
echo "=========================================="
echo "  Clips dir  : $CLIPS_DIR"
echo "  Layout     : $LAYOUT"
echo "  Output     : $OUTPUT"
echo "  Stride     : every ${STRIDE} frames ($(echo "scale=1; 15/$STRIDE" | bc)fps effective)"
echo "  Max frames : ${MAX_FRAMES:-unlimited}"
echo "  API URL    : ${API_URL:-<none, batch mode>}"
echo "  Clip start : $CLIP_START"
echo "=========================================="

# ── Run pipeline ───────────────────────────────────────────────────────────────
ARGS="--clips-dir \"$CLIPS_DIR\" --layout \"$LAYOUT\" --output \"$OUTPUT\" --clip-start \"$CLIP_START\" --stride \"$STRIDE\""

if [ "$MAX_FRAMES" -gt 0 ] 2>/dev/null; then
    ARGS="$ARGS --max-frames \"$MAX_FRAMES\""
fi

if [ -n "$API_URL" ]; then
    eval python -m pipeline.detect $ARGS --api-url "\"$API_URL\""
else
    eval python -m pipeline.detect $ARGS
fi

echo ""
echo "Done! Events written to: $OUTPUT"
echo "Event count: $(wc -l < "$OUTPUT" 2>/dev/null || echo 0)"

# ── If API is running, push any remaining events from the JSONL file ──────────
if [ -n "$API_URL" ] && [ -f "$OUTPUT" ]; then
    echo ""
    echo "Pushing all events to API (batch mode)..."
    python3 -c "
import json, httpx, sys

with open('$OUTPUT') as f:
    lines = [json.loads(l) for l in f if l.strip()]

batch_size = 500
pushed = 0
for i in range(0, len(lines), batch_size):
    batch = lines[i:i+batch_size]
    try:
        r = httpx.post('$API_URL/events/ingest', json={'events': batch}, timeout=30)
        body = r.json()
        pushed += body.get('accepted', 0)
        print(f'  Batch {i//batch_size + 1}: {r.status_code} — accepted={body.get(\"accepted\",0)} dup={body.get(\"duplicate\",0)}')
    except Exception as e:
        print(f'  Batch {i//batch_size + 1}: ERROR — {e}')

print(f'Total pushed: {pushed}/{len(lines)} events')
print(f'Dashboard: $API_URL')
"
fi

echo ""
echo "To replay events in simulated real time:"
echo "  python -m pipeline.replay --file $OUTPUT --api-url http://localhost:8000 --speed 10"
