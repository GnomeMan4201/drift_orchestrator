#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p data logs

JSONL="${1:-sample.jsonl}"

if [ ! -f "$JSONL" ]; then
    echo "ERROR: Input file not found: $JSONL"
    exit 1
fi

echo "=== drift_orchestrator eval ==="
echo "Input: $JSONL"
echo "Time:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo ""

python3 evaluator.py "$JSONL" 2>&1 | tee "logs/eval_$(date +%Y%m%d_%H%M%S).log"

echo ""
echo "=== DONE ==="
