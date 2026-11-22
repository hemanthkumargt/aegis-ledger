import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend import audit
from backend.db import get_engine, llm_outbound_log
from backend.main import app
from backend.mcp_ledger import ledger_totals
from backend.pii_vault import contains_raw_pii
from backend.scenarios import RAW_PII_VALUES, SCENARIOS

client = TestClient(app)


def process(name):
    sc = SCENARIOS[name]
    r = client.post("/disputes/process", json={"payload": sc["payload"], "simulate_429": sc["simulate_429"]})
    assert r.status_code == 200, r.text
    return r.json()


def test_valid_chargeback_auto_settles_and_no_pii_leaks():
    res = process("valid_180")
    assert res["status"] == "SETTLED"
    assert res["ledger_after"]["balances"]["ACC-C-1001"] == 118_000
    assert res["ledger_after"]["total_cents"] == res["ledger_before"]["total_cents"]
    with get_engine().connect() as c:
        payloads = [r[0] for r in c.execute(select(llm_outbound_log.c.payload)).all()]
    assert payloads and not any(contains_raw_pii(p) for p in payloads)
    assert not any(v in p for p in payloads for v in RAW_PII_VALUES)


def test_high_value_pauses_then_approval_moves_money():
    res = process("high_2500")
    assert res["status"] == "PENDING_APPROVAL"
    assert ledger_totals()["balances"]["ACC-C-1002"] == 100_000
    did = res["dispute_id"]
    assert client.post(f"/disputes/{did}/approve", json={}, headers={"X-Role": "analyst"}).status_code == 403
    assert ledger_totals()["balances"]["ACC-C-1002"] == 100_000
    ok = client.post(f"/disputes/{did}/approve", json={"operator": "maria"}, headers={"X-Role": "senior_approver"})
    assert ok.status_code == 200 and ok.json()["status"] == "SETTLED"
    assert ledger_totals()["balances"]["ACC-C-1002"] == 350_000
    assert client.post(f"/disputes/{did}/approve", json={}, headers={"X-Role": "senior_approver"}).status_code == 409


def test_reject_leaves_ledger_untouched():
    did = process("cross_border_90")["dispute_id"]
    r = client.post(f"/disputes/{did}/reject", json={"operator": "maria"}, headers={"X-Role": "senior_approver"})
    assert r.json()["status"] == "REJECTED" and ledger_totals()["balances"]["ACC-C-1005"] == 100_000


def test_prompt_injection_rejected_and_alert_logged():
    before = ledger_totals()["balances"]
    res = process("injection")
    assert res["status"] == "REJECTED_SECURITY"
    after = ledger_totals()["balances"]
    assert {k: v for k, v in after.items()} == before  # no balance moved
    types = [e["event_type"] for e in audit.list_events(500)]
    assert "security.alert" in types
    assert "GB82" not in json.dumps(client.get("/llm/outbound").json())


def test_flaky_429_recovers_with_single_ledger_entry():
    res = process("flaky_429")
    assert res["status"] == "SETTLED"
    assert ledger_totals()["balances"]["ACC-C-1004"] == 107_500
    assert client.get("/metrics").json()["rate_limit_retries"] == 2
    assert client.get("/ledger").json()["entries_balanced"] is True


def test_audit_endpoints_and_sse_headers():
    process("valid_180")
    v = client.get("/audit/verify").json()
    assert v["valid"] and v["length"] >= 5
    m = client.get("/metrics").json()
    assert m["pii_redactions"] == 2 and m["engine"].startswith("MOCK")
    assert client.get("/harbor/results").status_code == 200


def test_transient_provider_errors_trigger_failover():
    from backend.llm_factory import is_rate_limit
    assert is_rate_limit(Exception("429 RESOURCE_EXHAUSTED"))
    assert is_rate_limit(Exception("503 UNAVAILABLE: model is currently experiencing high demand"))
    assert not is_rate_limit(ValueError("invalid schema"))


def test_swallowed_provider_error_payload_is_raised():
    import pytest
    from backend.llm_factory import raise_if_error_content
    with pytest.raises(RuntimeError):
        raise_if_error_content('{\n  "error": {"code": 503, "status": "UNAVAILABLE"}\n}')
    assert raise_if_error_content("plain narrative") == "plain narrative"
