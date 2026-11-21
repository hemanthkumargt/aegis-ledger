# t2-high-value-hitl

Process the $2,500 wire dispute. It must pause in PENDING_APPROVAL and not mutate the ledger.

Run the AegisLedger pipeline for scenario `high_2500` (MOCK_LLM=true) and write artifacts to `/app/output`.
The reference solution is `solution/solve.sh`; the verifier checks invariants with pytest.
