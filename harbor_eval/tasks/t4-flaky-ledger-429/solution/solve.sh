#!/bin/bash
set -euo pipefail
cd /app
python -m backend.run_scenario flaky_429 --out /app/output
