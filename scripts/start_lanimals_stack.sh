#!/usr/bin/env bash
set -u
cd ~/research_hub/repos/drift_orchestrator || exit 1
source .venv_graph/bin/activate

pkill -f "ui/lanimals_live.py" 2>/dev/null || true
pkill -f "alerts/runtime_alerts.py" 2>/dev/null || true

nohup .venv_graph/bin/python ui/lanimals_live.py > /tmp/lanimals_live.log 2>&1 &
nohup bash scripts/run_alert_loop.sh > /tmp/lanimals_alerts.log 2>&1 &

sleep 2
echo "UI:     http://127.0.0.1:8099"
echo "ALERTS: /tmp/lanimals_alerts.log"
echo "TRACE:  results/trace_log.jsonl"
echo "GRAPH:  results/trace_graph.gexf"
