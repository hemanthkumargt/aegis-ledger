"""Offline Harbor-equivalent runner (no Docker): executes each task's solve.sh logic and verifier.

Produces harbor_eval/results.json consumed by the UI (`/harbor/results`).
Usage: python -m harbor_eval.local_runner
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "harbor_eval" / "tasks"


def run_task(task_dir: Path) -> dict:
    solve = (task_dir / "solution" / "solve.sh").read_text()
    m = re.search(r"python -m backend.run_scenario (\S+) --out \S+( --approve)?", solve)
    scenario, approve = m.group(1), bool(m.group(2))
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "MOCK_LLM": "true", "LEDGER_BACKOFF_S": "0", "PYTHONPATH": str(ROOT),
               "DATABASE_URL": f"sqlite:///{tmp}/h.db", "AEGIS_OUTPUT_DIR": f"{tmp}/out"}
        t0 = time.time()
        cmd = [sys.executable, "-m", "backend.run_scenario", scenario, "--out", f"{tmp}/out"] + (["--approve"] if approve else [])
        agent = subprocess.run(cmd, env=env, cwd=ROOT, capture_output=True, text=True)
        if agent.returncode != 0:
            return {"task": task_dir.name, "passed": False, "assertions": [], "error": agent.stderr[-500:]}
        ver = subprocess.run([sys.executable, "-m", "pytest", str(task_dir / "tests" / "test_outputs.py"), "-v",
                              "--no-header", "-p", "no:cacheprovider"], env=env, cwd=ROOT, capture_output=True, text=True)
    assertions = [{"name": n, "passed": s == "PASSED"} for n, s in
                  re.findall(r"test_outputs\.py::(\w+) (PASSED|FAILED|ERROR)", ver.stdout)]
    return {"task": task_dir.name, "scenario": scenario, "passed": ver.returncode == 0, "assertions": assertions,
            "seconds": round(time.time() - t0, 2)}


def main() -> int:
    results = [run_task(d) for d in sorted(TASKS.iterdir()) if d.is_dir()]
    score = sum(r["passed"] for r in results) / max(len(results), 1)
    out = {"runner": "local", "score": score, "tasks": results}
    (ROOT / "harbor_eval" / "results.json").write_text(json.dumps(out, indent=2))
    for r in results:
        print(("PASS " if r["passed"] else "FAIL ") + r["task"])
    print(f"score={score:.2f}")
    return 0 if score == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
