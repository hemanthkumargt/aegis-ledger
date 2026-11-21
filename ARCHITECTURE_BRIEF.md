# AegisLedger — Architecture Brief (client deliverable)

## Objective
Automate triage of chargebacks / wire disputes while meeting PCI-DSS and GDPR data-minimisation duties and
guaranteeing that an LLM can never, on its own, move money.

## Flow
```
raw dispute ─► PII Tokenizer (vault) ─► LLM Gateway (screen + log) ─► IntakeExtractorAgent
                                                               │
                         InjectionGuard ◄──────────────────────┘
                              │
                    ComplianceAuditorAgent (deterministic policy)
                    ├─ ≤ $500, domestic ─► Ledger MCP (RBAC, idempotent) ─► SETTLED
                    ├─ > $500 / cross-border / hold ─► PENDING_APPROVAL ─► senior_approver ─► Ledger
                    └─ injection indicators ─► REJECTED_SECURITY + merchant hold
every step ─► audit_events (SHA-256 chain)
```

## Key design decisions
- **The model proposes, code disposes.** Policy, HITL and RBAC are enforced in code *and* again inside the
  ledger server (an `analyst` role physically cannot execute a refund over $500).
- **Refund destination is not a parameter.** `execute_refund(txn_id, amount, idempotency_key)` always credits the
  original payer, so "refund to attacker account" is structurally impossible.
- **Idempotency** key per dispute makes 429-retries safe (no double credit).
- **Outbound screening**: the gateway re-scans every prompt; a raw PII hit blocks the call and is audited.
- **Audit log stores hashes/tokens only** – never raw payloads.

## Threat model
| Threat | Control |
|---|---|
| PII exfiltration to LLM vendor | Tokenization before prompt build; gateway re-scan; Harbor asserts zero raw values in `llm_outbound_log` |
| Prompt injection in invoice text | Untrusted-data delimiting, regex guard, no LLM authority over refunds, merchant quarantine |
| Privilege escalation | Role scopes in ledger server; approval requires `senior_approver` |
| Double spend on retry | Idempotency key + atomic DB transaction |
| Log tampering | Hash chain; `/audit/verify` pinpoints first broken block |
| Over-refund | Refund ≤ original amount minus prior refunds |

## SLA targets (design targets, not measured production figures)
| Metric | Target |
|---|---|
| Auto-settle path p95 (excl. LLM) | < 300 ms |
| LLM extraction p95 | < 3 s (Groq typically sub-second) |
| HITL queue visibility | < 1 s via SSE |
| Audit verification | O(n), < 1 s per 10k events |

## Known limits / next steps
- Auth is header-based (`X-Role`) for demo; production needs OIDC + signed role claims.
- Vault key via `VAULT_KEY` env; production should use Cloud KMS envelope encryption.
- Audit chain integrity is detect-only; anchor the head hash to an external store (e.g. Cloud Storage object lock) for non-repudiation.
- Regex PII detection covers PAN/IBAN/SSN/email only; names/addresses need an NER pass (Presidio).
- Live Gemini/Groq paths use Agno but were not exercised in CI (needs keys); the mock path is what tests cover.
