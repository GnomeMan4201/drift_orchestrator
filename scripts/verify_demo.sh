#!/usr/bin/env bash
set -euo pipefail

FILE=$(ls -t demo_recordings/*.txt | head -n1)

echo "[*] Checking latest recording: $FILE"

grep -q "\[ROLLBACK\]" "$FILE" || { echo "FAIL: no rollback"; exit 1; }
grep -q "\[RECOVERY\]" "$FILE" || { echo "FAIL: no recovery"; exit 1; }
grep -q "\[TURN" "$FILE" || { echo "FAIL: no turns"; exit 1; }

echo "PASS: demo shows drift control behavior"
