#!/usr/bin/env bash
set -u
pkill -f "ui/lanimals_live.py" 2>/dev/null || true
pkill -f "alerts/runtime_alerts.py" 2>/dev/null || true
pkill -f "scripts/run_alert_loop.sh" 2>/dev/null || true
echo "LANimals stack stopped"
