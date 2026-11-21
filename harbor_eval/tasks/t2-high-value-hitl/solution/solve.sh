#!/bin/bash
set -euo pipefail
cd /app
python -m backend.run_scenario high_2500 --out /app/output
