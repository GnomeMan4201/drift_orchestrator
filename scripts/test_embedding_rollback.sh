#!/usr/bin/env bash
set -u
cd ~/research_hub/repos/drift_orchestrator || exit 1
source .venv_graph/bin/activate

cat > results/lanimals_state.json <<'JSON'
{
  "host_risk": 0.20,
  "network_restrictiveness": 0.10,
  "tool_trust": 0.90,
  "anomaly_level": 0.05,
  "local_only": false
}
JSON

python3 - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from agents.multi_agent import Coordinator

c = Coordinator()
c.add_agent("researcher")

tests = [
    ("researcher", "Explain TCP simply.", 0.0),
    ("researcher", "Explain DNS simply.", 0.0),
    ("researcher", "Explain UDP simply.", 0.0),
    ("researcher", "Explain DNS simply.", 0.35),
]

for agent, prompt, drift in tests:
    print("\n---")
    print(c.run(agent, prompt, drift))
PY
