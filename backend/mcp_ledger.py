"""MCP-style double-entry ledger tool server with RBAC and idempotent refunds.

Tools are described by JSON schemas (`TOOL_SPECS`, MCP `tools/list` shape) and invoked through
`LedgerServer.call`. Every mutation is atomic and idempotent, so retries after a 429 can never
double-credit an account.
"""
from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable

from sqlalchemy import func, insert, select, update

from .db import accounts, get_engine, ledger_entries, now_iso, refunds, transactions

SMALL_REFUND_LIMIT_CENTS = 50_000  # $500.00

ROLE_SCOPES: dict[str, set[str]] = {
    "analyst": {"read:ledger", "flag:hold", "refund:small"},
    "senior_approver": {"read:ledger", "flag:hold", "refund:small", "refund:any"},
}

TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "get_account_balance", "scope": "read:ledger",
     "description": "Return the balance (cents) of an account.",
     "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "get_transaction_history", "scope": "read:ledger",
     "description": "Return transactions involving an account.",
     "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}}, "required": ["account_id"]}},
    {"name": "execute_refund", "scope": "refund:small|refund:any",
     "description": "Refund (part of) a transaction back to the ORIGINAL payer. Destination cannot be chosen.",
     "inputSchema": {"type": "object", "properties": {"txn_id": {"type": "string"},
                                                       "amount_cents": {"type": "integer"},
                                                       "idempotency_key": {"type": "string"}},
                     "required": ["txn_id", "amount_cents", "idempotency_key"]}},
    {"name": "flag_compliance_hold", "scope": "flag:hold",
     "description": "Place a compliance hold on an account.",
     "inputSchema": {"type": "object", "properties": {"account_id": {"type": "string"}, "reason": {"type": "string"}},
                     "required": ["account_id", "reason"]}},
]


class RateLimitError(Exception):
    status_code = 429


class PermissionDenied(Exception):
    pass


class LedgerError(Exception):
    pass


def seed_ledger() -> None:
    """Idempotently seed demo accounts and transactions."""
    engine = get_engine()
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(accounts)).scalar_one():
            return
        conn.execute(insert(accounts), [
            dict(id="ACC-C-1001", owner="Customer 1001", kind="customer", balance_cents=100_000, country="US", hold=False),
            dict(id="ACC-C-1002", owner="Customer 1002", kind="customer", balance_cents=100_000, country="US", hold=False),
            dict(id="ACC-C-1003", owner="Customer 1003", kind="customer", balance_cents=100_000, country="US", hold=False),
            dict(id="ACC-C-1004", owner="Customer 1004", kind="customer", balance_cents=100_000, country="US", hold=False),
            dict(id="ACC-C-1005", owner="Customer 1005", kind="customer", balance_cents=100_000, country="GB", hold=False),
            dict(id="ACC-M-77", owner="Northwind Merchant", kind="merchant", balance_cents=5_000_000, country="US", hold=False),
        ])
        ts = now_iso()
        conn.execute(insert(transactions), [
            dict(id="TXN-1001", payer_account="ACC-C-1001", merchant_account="ACC-M-77", amount_cents=18_000, currency="USD", description="Headphones", posted_at=ts),
            dict(id="TXN-2002", payer_account="ACC-C-1002", merchant_account="ACC-M-77", amount_cents=250_000, currency="USD", description="Enterprise license", posted_at=ts),
            dict(id="TXN-3003", payer_account="ACC-C-1003", merchant_account="ACC-M-77", amount_cents=12_000, currency="USD", description="Subscription", posted_at=ts),
            dict(id="TXN-4004", payer_account="ACC-C-1004", merchant_account="ACC-M-77", amount_cents=7_500, currency="USD", description="Gift card", posted_at=ts),
            dict(id="TXN-5005", payer_account="ACC-C-1005", merchant_account="ACC-M-77", amount_cents=9_000, currency="USD", description="Cross-border order", posted_at=ts),
        ])


def ledger_totals() -> dict[str, Any]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(accounts.c.id, accounts.c.balance_cents, accounts.c.hold)).all()
    balances = {r[0]: r[1] for r in rows}
    return {"balances": balances, "total_cents": sum(balances.values()),
            "holds": [r[0] for r in rows if r[2]]}


def entries_balanced() -> bool:
    """Double-entry invariant: debits == credits across the whole entry table."""
    with get_engine().connect() as conn:
        d = conn.execute(select(func.coalesce(func.sum(ledger_entries.c.amount_cents), 0))
                         .where(ledger_entries.c.direction == "debit")).scalar_one()
        c = conn.execute(select(func.coalesce(func.sum(ledger_entries.c.amount_cents), 0))
                         .where(ledger_entries.c.direction == "credit")).scalar_one()
    return d == c


class LedgerServer:
    """Ledger tool server. `inject_429` makes the next N mutating calls fail with HTTP 429."""

    def __init__(self, inject_429: int = 0) -> None:
        self.inject_429 = inject_429
        self.attempts = 0
        self._tools: dict[str, Callable[..., dict[str, Any]]] = {
            "get_account_balance": self.get_account_balance,
            "get_transaction_history": self.get_transaction_history,
            "execute_refund": self.execute_refund,
            "flag_compliance_hold": self.flag_compliance_hold,
        }

    @staticmethod
    def list_tools() -> list[dict[str, Any]]:
        return TOOL_SPECS

    def call(self, name: str, args: dict[str, Any], role: str) -> dict[str, Any]:
        if name not in self._tools:
            raise LedgerError(f"unknown tool {name}")
        scopes = ROLE_SCOPES.get(role)
        if scopes is None:
            raise PermissionDenied(f"unknown role {role}")
        needed = {"get_account_balance": "read:ledger", "get_transaction_history": "read:ledger",
                  "flag_compliance_hold": "flag:hold", "execute_refund": "refund:small"}[name]
        if needed not in scopes:
            raise PermissionDenied(f"role {role} lacks scope {needed}")
        return self._tools[name](_role=role, **args)

    # -- read tools -----------------------------------------------------------------
    def get_account_balance(self, account_id: str, _role: str = "analyst") -> dict[str, Any]:
        with get_engine().connect() as conn:
            row = conn.execute(select(accounts).where(accounts.c.id == account_id)).mappings().first()
        if not row:
            raise LedgerError(f"account {account_id} not found")
        return {"account_id": account_id, "balance_cents": row["balance_cents"], "hold": bool(row["hold"])}

    def get_transaction_history(self, account_id: str, _role: str = "analyst") -> dict[str, Any]:
        with get_engine().connect() as conn:
            rows = conn.execute(select(transactions).where(
                (transactions.c.payer_account == account_id) | (transactions.c.merchant_account == account_id)
            )).mappings().all()
        return {"account_id": account_id, "transactions": [dict(r) for r in rows]}

    # -- write tools ----------------------------------------------------------------
    def flag_compliance_hold(self, account_id: str, reason: str, _role: str = "analyst") -> dict[str, Any]:
        with get_engine().begin() as conn:
            res = conn.execute(update(accounts).where(accounts.c.id == account_id)
                               .values(hold=True, hold_reason=reason))
        if not res.rowcount:
            raise LedgerError(f"account {account_id} not found")
        return {"account_id": account_id, "hold": True, "reason": reason}

    def execute_refund(self, txn_id: str, amount_cents: int, idempotency_key: str,
                       _role: str = "analyst") -> dict[str, Any]:
        self.attempts += 1
        if self.inject_429 > 0:
            self.inject_429 -= 1
            raise RateLimitError("429 Too Many Requests (simulated)")
        if amount_cents <= 0:
            raise LedgerError("amount must be positive")
        if amount_cents > SMALL_REFUND_LIMIT_CENTS and "refund:any" not in ROLE_SCOPES[_role]:
            raise PermissionDenied(f"role {_role} may not refund above ${SMALL_REFUND_LIMIT_CENTS / 100:.2f}")
        with get_engine().begin() as conn:
            prior = conn.execute(select(refunds).where(refunds.c.idempotency_key == idempotency_key)).mappings().first()
            if prior:
                return {"status": "duplicate_ignored", "entry_group": prior["entry_group"],
                        "amount_cents": prior["amount_cents"], "txn_id": txn_id}
            txn = conn.execute(select(transactions).where(transactions.c.id == txn_id)).mappings().first()
            if not txn:
                raise LedgerError(f"transaction {txn_id} not found")
            already = conn.execute(select(func.coalesce(func.sum(refunds.c.amount_cents), 0))
                                   .where(refunds.c.txn_id == txn_id)).scalar_one()
            if already + amount_cents > txn["amount_cents"]:
                raise LedgerError("refund exceeds original transaction amount")
            group = f"GRP-{uuid.uuid4().hex[:10]}"
            ts = now_iso()
            conn.execute(update(accounts).where(accounts.c.id == txn["merchant_account"])
                         .values(balance_cents=accounts.c.balance_cents - amount_cents))
            conn.execute(update(accounts).where(accounts.c.id == txn["payer_account"])
                         .values(balance_cents=accounts.c.balance_cents + amount_cents))
            conn.execute(insert(ledger_entries), [
                dict(entry_group=group, account_id=txn["merchant_account"], direction="debit",
                     amount_cents=amount_cents, ref=txn_id, created_at=ts),
                dict(entry_group=group, account_id=txn["payer_account"], direction="credit",
                     amount_cents=amount_cents, ref=txn_id, created_at=ts),
            ])
            conn.execute(insert(refunds).values(idempotency_key=idempotency_key, txn_id=txn_id,
                                                amount_cents=amount_cents, entry_group=group, actor_role=_role))
        return {"status": "refunded", "entry_group": group, "amount_cents": amount_cents, "txn_id": txn_id,
                "credited_account": txn["payer_account"]}


def call_with_retry(server: LedgerServer, name: str, args: dict[str, Any], role: str,
                    on_retry: Callable[[int, float], None] | None = None,
                    max_attempts: int = 5) -> dict[str, Any]:
    """Call a ledger tool, retrying 429s with exponential backoff (safe: mutations are idempotent)."""
    base = float(os.getenv("LEDGER_BACKOFF_S", "0.2"))
    for attempt in range(1, max_attempts + 1):
        try:
            return server.call(name, args, role)
        except RateLimitError:
            if attempt == max_attempts:
                raise
            delay = base * (2 ** (attempt - 1))
            if on_retry:
                on_retry(attempt, delay)
            time.sleep(delay)
    raise RuntimeError("unreachable")
