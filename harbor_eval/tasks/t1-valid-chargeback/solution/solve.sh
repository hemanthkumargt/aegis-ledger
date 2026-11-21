#!/bin/bash
set -euo pipefail
cd /app
python -m backend.run_scenario valid_180 --out /app/output
