"""Deterministic, reversible PII tokenizer backed by the database.

Raw PAN / IBAN / SSN / email values are replaced with stable tokens such as
``<PAN_001>``. The raw value is stored encrypted (Fernet / AES-128-CBC+HMAC) and
looked up deterministically through an HMAC so the same value always maps to the
same token. Only tokens are ever placed in an LLM prompt.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import threading
from dataclasses import dataclass

from cryptography.fernet import Fernet
from sqlalchemy import func, insert, select
from sqlalchemy.exc import IntegrityError

from .db import get_engine, now_iso, vault_entries

_DEV_SECRET = "aegis-dev-only-vault-secret-change-me"

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,3})?\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_PAN_RE = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_TOKEN_RE = re.compile(r"<(PAN|IBAN|SSN|EMAIL)_(\d{3,})>")

# Order matters: IBAN first (contains digit runs), then SSN, PAN, EMAIL.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", _EMAIL_RE),
    ("IBAN", _IBAN_RE),
    ("SSN", _SSN_RE),
    ("PAN", _PAN_RE),
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _iban_ok(raw: str) -> bool:
    s = raw.replace(" ", "")
    if not 15 <= len(s) <= 34:
        return False
    rearranged = s[4:] + s[:4]
    try:
        num = "".join(str(int(c, 36)) for c in rearranged)
        return int(num) % 97 == 1
    except ValueError:
        return False


def _valid(kind: str, raw: str) -> bool:
    if kind == "PAN":
        digits = re.sub(r"[ -]", "", raw)
        return 13 <= len(digits) <= 19 and _luhn_ok(digits)
    if kind == "IBAN":
        return _iban_ok(raw)
    return True


@dataclass(frozen=True)
class Finding:
    kind: str
    value: str
    start: int
    end: int


def detect(text: str) -> list[Finding]:
    """Return all PII findings in ``text`` (non-overlapping, validated)."""
    findings: list[Finding] = []
    taken: list[tuple[int, int]] = []
    for kind, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            s, e = m.span()
            if any(s < te and e > ts for ts, te in taken):
                continue
            if not _valid(kind, m.group(0)):
                continue
            taken.append((s, e))
            findings.append(Finding(kind, m.group(0), s, e))
    findings.sort(key=lambda f: f.start)
    return findings


def contains_raw_pii(text: str) -> bool:
    return bool(detect(text))


class PiiVault:
    def __init__(self) -> None:
        secret = os.getenv("VAULT_KEY", _DEV_SECRET)
        digest = hashlib.sha256(secret.encode()).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))
        self._hmac_key = hashlib.sha256(b"lookup|" + digest).digest()
        self._lock = threading.Lock()

    @staticmethod
    def _normalize(kind: str, raw: str) -> str:
        if kind in ("PAN", "IBAN"):
            return re.sub(r"[ -]", "", raw).upper()
        return raw.strip().lower() if kind == "EMAIL" else raw.strip()

    def _lookup_hash(self, kind: str, raw: str) -> str:
        msg = f"{kind}|{self._normalize(kind, raw)}".encode()
        return hmac.new(self._hmac_key, msg, hashlib.sha256).hexdigest()

    def _token_for(self, kind: str, raw: str) -> str:
        lookup = self._lookup_hash(kind, raw)
        engine = get_engine()
        with self._lock:
            for _ in range(5):
                with engine.begin() as conn:
                    row = conn.execute(
                        select(vault_entries.c.token).where(vault_entries.c.lookup_hash == lookup)
                    ).first()
                    if row:
                        return row[0]
                    count = conn.execute(
                        select(func.count()).select_from(vault_entries).where(vault_entries.c.kind == kind)
                    ).scalar_one()
                    token = f"<{kind}_{count + 1:03d}>"
                    try:
                        conn.execute(
                            insert(vault_entries).values(
                                token=token,
                                kind=kind,
                                lookup_hash=lookup,
                                ciphertext=self._fernet.encrypt(raw.encode()).decode(),
                                created_at=now_iso(),
                            )
                        )
                        return token
                    except IntegrityError:
                        continue
        raise RuntimeError("could not allocate PII token")

    def tokenize(self, text: str) -> tuple[str, dict[str, int]]:
        """Replace every PII value with a token. Returns (safe_text, counts_by_kind)."""
        counts: dict[str, int] = {}
        out: list[str] = []
        last = 0
        for f in detect(text):
            out.append(text[last : f.start])
            out.append(self._token_for(f.kind, f.value))
            counts[f.kind] = counts.get(f.kind, 0) + 1
            last = f.end
        out.append(text[last:])
        return "".join(out), counts

    def detokenize(self, text: str) -> str:
        """Restore raw values. Only call from trusted, operator-facing code paths."""
        engine = get_engine()

        def repl(m: re.Match[str]) -> str:
            token = m.group(0)
            with engine.begin() as conn:
                row = conn.execute(
                    select(vault_entries.c.ciphertext).where(vault_entries.c.token == token)
                ).first()
            return self._fernet.decrypt(row[0].encode()).decode() if row else token

        return _TOKEN_RE.sub(repl, text)
