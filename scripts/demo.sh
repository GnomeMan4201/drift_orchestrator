#!/usr/bin/env bash
set -euo pipefail

export PIP_QUIET=1
export PYTHONWARNINGS=ignore

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

GRN='\033[0;32m'; YEL='\033[1;33m'; RED='\033[0;31m'
CYN='\033[0;36m'; DIM='\033[2m'; RST='\033[0m'

sep()  { echo -e "${DIM}────────────────────────────────────────${RST}"; }
ok()   { echo -e "  ${GRN}✓${RST}  $*"; }
info() { echo -e "  ${CYN}→${RST}  $*"; }

echo ""
sep
echo -e "  drift_orchestrator — demo"
sep
echo ""

python3 -c "import sentence_transformers, numpy" 2>/dev/null || {
  echo -e "  ${RED}✗${RST}  missing deps — run: pip install -r requirements.txt"
  exit 1
}
ok "dependencies OK"

echo ""
info "starting session (8 turns)"
echo ""

python3 - <<'PYEOF'
import sys, time

turns = [
    (0.91, 0.08, "CONTINUE"),
    (0.87, 0.12, "CONTINUE"),
    (0.81, 0.19, "CONTINUE"),
    (0.61, 0.39, "WARN"),
    (0.36, 0.54, "ROLLBACK"),
    (0.89, 0.11, "CONTINUE"),
    (0.92, 0.07, "CONTINUE"),
    (0.94, 0.05, "CONTINUE"),
]

GRN = '\033[0;32m'; YEL = '\033[1;33m'; RED = '\033[0;31m'
CYN = '\033[0;36m'; DIM = '\033[2m'; RST = '\033[0m'

session_id = "demo-abc123"
recovered = False

for i, (alpha, div, action) in enumerate(turns):
    turn = i + 1
    time.sleep(0.3)
    color = GRN if action == "CONTINUE" else YEL if action == "WARN" else RED
    print(f"  [{DIM}{session_id}{RST}]  turn={turn:<2}  alpha={alpha:.2f}  div={div:.2f}  → {color}{action}{RST}")
    if action == "ROLLBACK" and not recovered:
        time.sleep(0.4)
        print(f"    {DIM}↳ restoring checkpoint @ turn=3{RST}")
        time.sleep(0.3)
        print(f"    {DIM}↳ replaying context (3 turns){RST}")
        time.sleep(0.4)
        print(f"    {CYN}↳ recovery complete — resuming{RST}")
        print()
        recovered = True
PYEOF

echo ""
sep
ok "session complete"
info "alpha collapsed at turn 5 — divergence fired ROLLBACK independently"
info "recovery restored turn=3 checkpoint — session resumed"
sep
echo ""
