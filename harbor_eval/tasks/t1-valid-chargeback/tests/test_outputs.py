"""Harbor verifier for t1-valid-chargeback. Reads artifacts produced by solution/solve.sh."""
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

def test_auto_settles(art):
    assert art["result"]["status"] == "SETTLED"
    assert art["ledger_final"]["balances"]["ACC-C-1001"] == 118_000

def test_zero_pii_in_llm_logs(art, outbound):
    assert outbound, "LLM gateway must have logged at least one call"
    for payload in outbound:
        for raw in RAW_PII:
            assert raw not in payload, f"raw PII leaked: {raw}"

def test_ledger_invariants(art):
    assert art["ledger_final"]["total_cents"] == art["ledger_before"]["total_cents"]
    assert art["entries_balanced"] is True
    assert art["audit"]["valid"] is True
