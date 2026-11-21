#!/bin/bash
# Harbor verifier entrypoint: writes 1/0 reward.
mkdir -p /logs/verifier
pip install -q pytest >/dev/null 2>&1 || true
if python -m pytest /tests/test_outputs.py -q; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
