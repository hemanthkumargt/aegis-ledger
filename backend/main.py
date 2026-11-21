"""AegisLedger FastAPI service (REST + SSE)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from . import audit
from .agents import (DisputePipeline, get_dispute, list_disputes, metrics, reset_runtime, resolve_dispute)
from .db import accounts, get_engine, llm_outbound_log, reset_engine
from .events import bus
from .llm_factory import active_engine_label, mock_enabled
from .mcp_ledger import (LedgerError, PermissionDenied, TOOL_SPECS, entries_balanced, ledger_totals, seed_ledger)
from .scenarios import SCENARIOS

@asynccontextmanager
async def lifespan(_: FastAPI):
    get_engine()
    seed_ledger()
    yield


app = FastAPI(title="AegisLedger", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


class ProcessRequest(BaseModel):
    payload: str = Field(min_length=1, max_length=20_000)
    simulate_429: int = Field(0, ge=0, le=4, description="Demo hook: ledger returns 429 this many times")


class ResolveRequest(BaseModel):
    operator: str = "operator"


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "engine": active_engine_label(), "mock": mock_enabled()}


@app.get("/scenarios")
def scenarios() -> dict[str, Any]:
    return SCENARIOS


@app.post("/disputes/process")
def process(req: ProcessRequest, x_role: str = Header("analyst")) -> dict[str, Any]:
    return DisputePipeline(simulate_429=req.simulate_429).process(req.payload, role=x_role)


@app.get("/disputes")
def disputes() -> list[dict[str, Any]]:
    return list_disputes()


@app.get("/disputes/{dispute_id}")
def dispute(dispute_id: str) -> dict[str, Any]:
    d = get_dispute(dispute_id)
    if not d:
        raise HTTPException(404, "dispute not found")
    return d


def _resolve(dispute_id: str, approve: bool, req: ResolveRequest, role: str) -> dict[str, Any]:
    try:
        return resolve_dispute(dispute_id, approve, req.operator, role)
    except PermissionDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except LedgerError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/disputes/{dispute_id}/approve")
def approve(dispute_id: str, req: ResolveRequest, x_role: str = Header("analyst")) -> dict[str, Any]:
    return _resolve(dispute_id, True, req, x_role)


@app.post("/disputes/{dispute_id}/reject")
def reject(dispute_id: str, req: ResolveRequest, x_role: str = Header("analyst")) -> dict[str, Any]:
    return _resolve(dispute_id, False, req, x_role)


@app.get("/ledger")
def ledger() -> dict[str, Any]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(accounts)).mappings().all()
    return {"accounts": [dict(r) for r in rows], "total_cents": ledger_totals()["total_cents"],
            "entries_balanced": entries_balanced(), "tools": TOOL_SPECS}


@app.get("/audit")
def audit_list(limit: int = 100) -> list[dict[str, Any]]:
    return audit.list_events(limit)


@app.get("/audit/verify")
def audit_verify() -> dict[str, Any]:
    return audit.verify_chain()


@app.post("/audit/tamper-demo/{seq}")
def audit_tamper(seq: int) -> dict[str, Any]:
    if os.getenv("ALLOW_DEMO_TAMPER", "false").lower() != "true":
        raise HTTPException(403, "set ALLOW_DEMO_TAMPER=true to enable the tamper demo")
    return {"tampered": audit.tamper_for_demo(seq)}


@app.get("/llm/outbound")
def llm_outbound(limit: int = 50) -> list[dict[str, Any]]:
    with get_engine().connect() as conn:
        rows = conn.execute(select(llm_outbound_log).order_by(llm_outbound_log.c.id.desc()).limit(limit)).mappings().all()
    return [dict(r) for r in rows]


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    return metrics.snapshot()


@app.get("/harbor/results")
def harbor_results() -> dict[str, Any]:
    path = Path(os.getenv("HARBOR_RESULTS", "harbor_eval/results.json"))
    if not path.exists():
        return {"available": False, "tasks": [], "hint": "run ./harbor_eval/run_harbor.sh"}
    return {"available": True, **json.loads(path.read_text())}


@app.post("/demo/reset")
def demo_reset() -> dict[str, Any]:
    """Wipe all state and reseed (demo/CI convenience)."""
    from .db import metadata
    engine = get_engine()
    metadata.drop_all(engine)
    reset_engine()
    reset_runtime()
    get_engine()
    seed_ledger()
    return {"reset": True}


@app.get("/stream/events")
async def stream_events(last_id: int = 0) -> StreamingResponse:
    async def gen():
        cursor = last_id
        idle = 0
        while True:
            events = bus.since(cursor)
            for ev in events:
                cursor = ev["id"]
                yield f"id: {ev['id']}\ndata: {json.dumps(ev)}\n\n"
            idle = 0 if events else idle + 1
            if idle % 100 == 99:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.15)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
