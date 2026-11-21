# t1-valid-chargeback

Process the standard $180 chargeback dispute. It must auto-settle and no raw PII may reach the LLM.

Run the AegisLedger pipeline for scenario `valid_180` (MOCK_LLM=true) and write artifacts to `/app/output`.
The reference solution is `solution/solve.sh`; the verifier checks invariants with pytest.
