#!/usr/bin/env bash
set -u
cd ~/research_hub/repos/drift_orchestrator || exit 1
source .venv_graph/bin/activate
while true; do
  python alerts/runtime_alerts.py
  sleep 2
done
