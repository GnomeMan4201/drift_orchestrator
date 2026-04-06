#!/usr/bin/env bash
set -u
cd ~/research_hub/repos/drift_orchestrator || exit 1

echo "== syntax =="
source .venv_graph/bin/activate
python -m py_compile \
  analysis/trace_logger.py \
  analysis/trace_to_graph.py \
  analysis/drift_analytics.py \
  analysis/attack_propagation.py \
  analysis/paper_ready_report.py \
  ui/lanimals_live.py \
  alerts/runtime_alerts.py \
  agents/multi_agent.py \
  firewall/gateway_wrapper.py

echo
echo "== endpoint =="
curl -s http://127.0.0.1:8099/api/trace | head -c 300 || true
echo

echo
echo "== gateway =="
curl -s http://127.0.0.1:8765/health || echo "gateway down"

echo
echo "== artifacts =="
ls -lh results/trace_log.jsonl results/trace_graph.gexf results/analytics 2>/dev/null || true
