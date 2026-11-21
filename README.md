# AegisLedger — Zero-Trust Payment Dispute & Regulatory Remediation Engine

Agno multi-agent dispute handling where **raw PII never reaches an LLM**, **refunds above $500 or cross-border
reversals pause for a human**, and **every step lands in a SHA-256 hash-chained audit log**. A Harbor suite
proves it. Ships with a dark "Risk Command Center" UI.

| Layer | Implementation |
|---|---|
| PII firewall | `backend/pii_vault.py` – Luhn/mod-97-validated PAN/IBAN/SSN/email → `<PAN_001>` tokens, Fernet-encrypted vault in the DB |
| Ledger tools | `backend/mcp_ledger.py` – MCP-style tool specs, double-entry, idempotent refunds, RBAC (`analyst` ≤ $500, `senior_approver` any), simulated 429s + backoff |
| Agents | `backend/agents.py` – `IntakeExtractorAgent`, `ComplianceAuditorAgent`, HITL gate, injection guard |
| Audit | `backend/audit.py` – hash chain, `/audit/verify` |
| API | `backend/main.py` – REST + SSE `/stream/events` |
| UI | `frontend/` – Next.js 15, Tailwind, Framer Motion |
| Eval | `harbor_eval/` – 4 Harbor tasks + offline runner |

## Project status
Built as a Forward Deployed AI Solutions Engineer portfolio project. Zero-trust PII handling, human-in-the-loop approval gates and a tamper-evident audit trail for payment disputes.
Verified offline: unit/integration tests and a Harbor-style evaluation suite using a deterministic `MOCK_LLM=true` mode.
The live Gemini/Groq paths are implemented through Agno's model classes with 429 failover; they require your own free API keys and are exercised separately from CI.

## Quickstart (offline, no keys, no Docker)
```bash
python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
MOCK_LLM=true pytest -q                      # 14 tests
./harbor_eval/run_harbor.sh                  # 4/4 tasks, writes harbor_eval/results.json
MOCK_LLM=true uvicorn backend.main:app --port 8000
```

## Docker (Postgres + backend + UI)
```bash
cp .env.example .env        # add GEMINI_API_KEY / GROQ_API_KEY, set MOCK_LLM=false for real models
docker compose up --build   # UI http://localhost:3000, API http://localhost:8000/docs
```
Free keys (no card): [Google AI Studio](https://aistudio.google.com) and [Groq](https://console.groq.com).
`LLM_PROVIDER=gemini` uses `gemini-2.5-flash-lite` and fails over to Groq `llama-3.3-70b-versatile` on HTTP 429
(and vice-versa). Override model ids with `GEMINI_MODEL` / `GROQ_MODEL`. Free-tier quotas change; check the
provider docs.

## Harbor
`./harbor_eval/run_harbor.sh` runs `harbor run -p harbor_eval/tasks --agent oracle` in Docker sandboxes when the
`harbor` CLI and Docker are installed; otherwise it runs the identical verifier tests through
`harbor_eval/local_runner.py`. Tasks: valid chargeback · $2,500 HITL pause · prompt injection · ledger 429 recovery.

## Deploy to GCP (scale-to-zero)
```bash
PROJECT_ID=my-proj GEMINI_API_KEY=... GROQ_API_KEY=... ./deploy_gcp.sh
```

## Demo script (60 seconds)
1. Click **Valid $180 Chargeback** → settles, PII panel shows `<PAN_001>` tokens.
2. **High-Value $2,500** → amber HITL card; try `analyst` role (403), then `senior_approver` → AUTHORIZE.
3. **Prompt Injection** → rejected, merchant account placed on hold, security alert in the stream.
4. **Flaky 429** → two retries, exactly one ledger entry pair.
5. **VERIFY CHAIN** → green; **TAMPER DEMO** then verify → red at the tampered block.
