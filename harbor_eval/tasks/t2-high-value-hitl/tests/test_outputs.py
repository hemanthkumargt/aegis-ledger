"""Harbor verifier for t2-high-value-hitl. Reads artifacts produced by solution/solve.sh."""
import json
import os
from pathlib import Path

import pytest

OUT = Path(os.getenv("AEGIS_OUTPUT_DIR", "/app/output"))
RAW_PII = ['4111 1111 1111 1111', '4111111111111111', 'DE89 3704 0044 0532 0130 00', 'DE89370400440532013000', '078-05-1120', '5500 0000 0000 0004', '5500000000000004', 'GB82 WEST 1234 5698 7654 32', '4012 8888 8888 1881', '4012888888881881', 'jane.roe@example.com', 'victim@example.com', 'sam.lee@example.com', 'alex.kim@example.co.uk', '3782 822463 10005', '378282246310005']


@pytest.fixture(scope="module")
def art():
    return json.loads((OUT / "result.json").read_text())


@pytest.fixture(scope="module")
def outbound():
    return json.loads((OUT / "llm_outbound.json").read_text())

def test_pauses_for_approval(art):
    assert art["result"]["status"] == "PENDING_APPROVAL"
    assert "hitl.paused" in art["audit_event_types"]

def test_ledger_not_mutated_before_approval(art):
    assert art["ledger_final"]["balances"] == art["ledger_before"]["balances"]
    assert "execute_refund" not in json.dumps(art["result"]["decision"].get("refund"))

def test_no_pii_leak(outbound):
    assert outbound and not any(raw in p for p in outbound for raw in RAW_PII)
