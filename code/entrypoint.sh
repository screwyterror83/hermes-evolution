#!/bin/bash
# Thin wrapper: pull latest self-evolution code, then dispatch to Python
set -e

cd /opt/self-evolution && git pull --quiet 2>/dev/null || true

if [ "$1" = "api" ]; then
    exec uvicorn evo_api.main:app --host 0.0.0.0 --port 8621 --app-dir /app
else
    exec python /app/runner.py "$@"
fi
