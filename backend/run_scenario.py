"""Run one scenario end-to-end and write Harbor-verifiable artifacts.

Usage: python -m backend.run_scenario <scenario> --out DIR [--approve]
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import select

from . import audit
from .agents import DisputePipeline, resolve_dispute
from .db import get_engine, llm_outbound_log
from .mcp_ledger import entries_balanced, ledger_totals, seed_ledger
from .scenarios import SCENARIOS


def run(name: str, out: Path, approve: bool = False) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    get_engine()
    seed_ledger()
    sc = SCENARIOS[name]
    before = ledger_totals()
    result = DisputePipeline(simulate_429=sc["simulate_429"]).process(sc["payload"])
    after_process = ledger_totals()
    if approve and result["status"] == "PENDING_APPROVAL":
        resolve_dispute(result["dispute_id"], True, "harbor-approver", "senior_approver")
    with get_engine().connect() as conn:
        outbound = [r["payload"] for r in conn.execute(select(llm_outbound_log)).mappings().all()]
    (out / "llm_outbound.json").write_text(json.dumps(outbound, indent=2))
    artifacts = {
        "scenario": name, "result": result, "ledger_before": before, "ledger_after_process": after_process,
        "ledger_final": ledger_totals(), "entries_balanced": entries_balanced(),
        "audit": audit.verify_chain(),
        "audit_event_types": [e["event_type"] for e in audit.list_events(500)],
    }
    (out / "result.json").write_text(json.dumps(artifacts, indent=2))
    return artifacts


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=sorted(SCENARIOS))
    ap.add_argument("--out", default=os.getenv("AEGIS_OUTPUT_DIR", "/app/output"))
    ap.add_argument("--approve", action="store_true")
    a = ap.parse_args()
    run(a.scenario, Path(a.out), a.approve)
