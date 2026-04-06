#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_NAME="$(basename "$REPO_ROOT")"
CAST="$REPO_ROOT/demo_recordings/demo.cast"
GIF="$REPO_ROOT/demo_recordings/demo.gif"

mkdir -p "$REPO_ROOT/demo_recordings"

echo ""
echo "  recording: $REPO_NAME"
echo "  output:    $GIF"
echo ""

asciinema rec "$CAST" \
  --command "$REPO_ROOT/scripts/demo.sh" \
  --title "$REPO_NAME demo" \
  --overwrite

agg "$CAST" "$GIF" \
  --font-size 14 \
  --speed 1.5

echo ""
echo "  done: $GIF ($(du -sh "$GIF" | cut -f1))"
echo ""
