import pytest

from backend import agents
from backend.db import reset_engine, get_engine
from backend.mcp_ledger import seed_ledger


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("MOCK_LLM", "true")
    monkeypatch.setenv("LEDGER_BACKOFF_S", "0")
    monkeypatch.setenv("STREAM_PACE_S", "0")
    reset_engine()
    agents.reset_runtime()
    get_engine()
    seed_ledger()
    yield
    reset_engine()
