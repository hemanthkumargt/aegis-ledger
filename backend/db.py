"""Database layer. PostgreSQL in Docker/Cloud Run, SQLite for offline tests."""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

metadata = MetaData()

vault_entries = Table(
    "vault_entries",
    metadata,
    Column("token", String(32), primary_key=True),
    Column("kind", String(16), nullable=False),
    Column("lookup_hash", String(64), nullable=False, unique=True),
    Column("ciphertext", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("owner", String(80), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("balance_cents", Integer, nullable=False),
    Column("country", String(2), nullable=False),
    Column("hold", Boolean, nullable=False, default=False),
    Column("hold_reason", Text, nullable=True),
)

transactions = Table(
    "transactions",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("payer_account", String(40), nullable=False),
    Column("merchant_account", String(40), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("description", Text, nullable=False),
    Column("posted_at", String(40), nullable=False),
)

ledger_entries = Table(
    "ledger_entries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("entry_group", String(40), nullable=False),
    Column("account_id", String(40), nullable=False),
    Column("direction", String(6), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("ref", String(60), nullable=False),
    Column("created_at", String(40), nullable=False),
)

refunds = Table(
    "refunds",
    metadata,
    Column("idempotency_key", String(80), primary_key=True),
    Column("txn_id", String(40), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("entry_group", String(40), nullable=False),
    Column("actor_role", String(24), nullable=False),
)

disputes = Table(
    "disputes",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("status", String(32), nullable=False),
    Column("txn_id", String(40), nullable=True),
    Column("amount_cents", Integer, nullable=True),
    Column("case_json", Text, nullable=False),
    Column("decision_json", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("seq", Integer, primary_key=True, autoincrement=False),
    Column("ts", String(40), nullable=False),
    Column("event_type", String(40), nullable=False),
    Column("actor", String(40), nullable=False),
    Column("dispute_id", String(40), nullable=True),
    Column("payload", Text, nullable=False),
    Column("prev_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False),
)

llm_outbound_log = Table(
    "llm_outbound_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String(40), nullable=False),
    Column("dispute_id", String(40), nullable=True),
    Column("provider", String(24), nullable=False),
    Column("payload", Text, nullable=False),
    Column("tokens_est", Integer, nullable=False),
    Column("latency_ms", Integer, nullable=False),
)

_lock = threading.RLock()
_engine: Engine | None = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./aegis.db")


def get_engine() -> Engine:
    global _engine
    with _lock:
        if _engine is None:
            url = database_url()
            kwargs: dict = {"future": True}
            if url.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False}
                if ":memory:" in url:
                    kwargs["poolclass"] = StaticPool
            else:
                kwargs["pool_pre_ping"] = True
            _engine = create_engine(url, **kwargs)
            metadata.create_all(_engine)
        return _engine


def reset_engine() -> None:
    """Dispose the engine (used by tests and `/demo/reset`)."""
    global _engine
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
