"""Tamper-evident, SHA-256 hash-chained audit log."""
from __future__ import annotations

import hashlib
import json
import threading
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .db import audit_events, get_engine, now_iso

GENESIS = "0" * 64
_lock = threading.Lock()


def canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_hash(prev_hash: str, seq: int, ts: str, event_type: str, actor: str,
                 dispute_id: str | None, payload_json: str) -> str:
    material = "|".join([prev_hash, str(seq), ts, event_type, actor, dispute_id or "", payload_json])
    return hashlib.sha256(material.encode()).hexdigest()


def append(event_type: str, actor: str, payload: dict[str, Any], dispute_id: str | None = None) -> dict[str, Any]:
    payload_json = canonical(payload)
    engine = get_engine()
    with _lock:
        for _ in range(5):
            try:
                with engine.begin() as conn:
                    last = conn.execute(
                        select(audit_events.c.seq, audit_events.c.hash)
                        .order_by(audit_events.c.seq.desc())
                        .limit(1)
                    ).first()
                    seq, prev = (last[0] + 1, last[1]) if last else (1, GENESIS)
                    ts = now_iso()
                    h = compute_hash(prev, seq, ts, event_type, actor, dispute_id, payload_json)
                    row = dict(seq=seq, ts=ts, event_type=event_type, actor=actor, dispute_id=dispute_id,
                               payload=payload_json, prev_hash=prev, hash=h)
                    conn.execute(audit_events.insert().values(**row))
                    return row
            except IntegrityError:
                continue  # another writer took this seq (multi-instance); retry
    raise RuntimeError("audit append failed")


def list_events(limit: int = 200) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(audit_events).order_by(audit_events.c.seq.desc()).limit(limit)).mappings().all()
    return [dict(r) for r in reversed(rows)]


def verify_chain() -> dict[str, Any]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(audit_events).order_by(audit_events.c.seq)).mappings().all()
    prev = GENESIS
    for i, r in enumerate(rows, start=1):
        expected = compute_hash(prev, r["seq"], r["ts"], r["event_type"], r["actor"], r["dispute_id"], r["payload"])
        if r["seq"] != i or r["prev_hash"] != prev or r["hash"] != expected:
            return {"valid": False, "length": len(rows), "broken_at": r["seq"], "head": prev}
        prev = r["hash"]
    return {"valid": True, "length": len(rows), "broken_at": None, "head": prev}


def tamper_for_demo(seq: int) -> bool:
    """Mutate a stored payload without re-hashing (demo of tamper detection only)."""
    with get_engine().begin() as conn:
        res = conn.execute(update(audit_events).where(audit_events.c.seq == seq).values(payload='{"tampered":true}'))
        return res.rowcount > 0
