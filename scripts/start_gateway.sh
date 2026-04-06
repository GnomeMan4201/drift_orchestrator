#!/usr/bin/env bash
set -u
cd ~/research_hub/repos/drift_orchestrator || exit 1
source .venv_graph/bin/activate
pkill -f "uvicorn firewall.gateway:app" 2>/dev/null || true
nohup .venv_graph/bin/python -m uvicorn firewall.gateway:app --host 127.0.0.1 --port 8765 > /tmp/drift_gateway.log 2>&1 &
sleep 2
curl -s http://127.0.0.1:8765/health || tail -n 80 /tmp/drift_gateway.log
