#!/bin/bash
set -euo pipefail
cd /app
python -m backend.run_scenario injection --out /app/output
