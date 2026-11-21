# t4-flaky-ledger-429

Ledger returns 429 twice. Recover gracefully with exactly one ledger entry pair.

Run the AegisLedger pipeline for scenario `flaky_429` (MOCK_LLM=true) and write artifacts to `/app/output`.
The reference solution is `solution/solve.sh`; the verifier checks invariants with pytest.
