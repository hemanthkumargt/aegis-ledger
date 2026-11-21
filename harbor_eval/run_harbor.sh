#!/usr/bin/env bash
# Runs the AegisLedger Harbor suite. Uses `harbor run` (Docker sandboxes) when available,
# otherwise the offline local runner that executes the same verifier tests.
set -euo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"

if command -v harbor >/dev/null 2>&1 && command -v docker >/dev/null 2>&1 && [ "${HARBOR_LOCAL:-0}" != "1" ]; then
  echo "== staging backend into each task environment =="
  for t in harbor_eval/tasks/*/; do
    rm -rf "$t/environment/backend"; cp -R backend "$t/environment/backend"
    cp requirements.txt "$t/environment/requirements.txt"
  done
  harbor run -p harbor_eval/tasks --agent oracle
  for t in harbor_eval/tasks/*/; do rm -rf "$t/environment/backend" "$t/environment/requirements.txt"; done
else
  echo "== harbor/docker not found (or HARBOR_LOCAL=1): running offline local runner =="
  PYTHONPATH=. "$PY" -m harbor_eval.local_runner
fi
