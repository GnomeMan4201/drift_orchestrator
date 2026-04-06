#!/usr/bin/env bash
set -u
pkill -f "uvicorn firewall.gateway:app" 2>/dev/null || true
echo "gateway stopped"
