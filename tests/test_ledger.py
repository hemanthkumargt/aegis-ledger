import pytest

from backend.mcp_ledger import (LedgerServer, PermissionDenied, call_with_retry, entries_balanced, ledger_totals,
                                RateLimitError)


def test_rbac_blocks_analyst_large_refund():
    with pytest.raises(PermissionDenied):
        LedgerServer().call("execute_refund", {"txn_id": "TXN-2002", "amount_cents": 250_000, "idempotency_key": "k"}, "analyst")
    assert ledger_totals()["balances"]["ACC-C-1002"] == 100_000


def test_refund_is_double_entry_idempotent_and_capped():
    s = LedgerServer()
    total = ledger_totals()["total_cents"]
    args = {"txn_id": "TXN-1001", "amount_cents": 18_000, "idempotency_key": "k1"}
    assert s.call("execute_refund", args, "analyst")["status"] == "refunded"
    assert s.call("execute_refund", args, "analyst")["status"] == "duplicate_ignored"
    t = ledger_totals()
    assert t["balances"]["ACC-C-1001"] == 118_000 and t["total_cents"] == total and entries_balanced()
    with pytest.raises(Exception):
        s.call("execute_refund", {**args, "idempotency_key": "k2"}, "analyst")  # exceeds original amount


def test_retry_recovers_from_429_without_duplicates():
    s = LedgerServer(inject_429=2)
    args = {"txn_id": "TXN-4004", "amount_cents": 7_500, "idempotency_key": "k"}
    assert call_with_retry(s, "execute_refund", args, "analyst")["status"] == "refunded"
    assert s.attempts == 3 and ledger_totals()["balances"]["ACC-C-1004"] == 107_500


def test_retry_gives_up_after_max_attempts():
    with pytest.raises(RateLimitError):
        call_with_retry(LedgerServer(inject_429=9), "execute_refund",
                        {"txn_id": "TXN-4004", "amount_cents": 1, "idempotency_key": "z"}, "analyst", max_attempts=3)
