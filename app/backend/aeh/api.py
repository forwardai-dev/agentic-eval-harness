"""FastAPI app wiring every route: golden set, run, runs, eval, verify, /mcp.

Testable end-to-end via `fastapi.testclient.TestClient` — no live server
needed for the pytest suite. CORS is open so the static `index.html`
dashboard can call this API from `file://` or any static server.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import evidence, mcp
from .eval import summarize
from .golden import golden_by_id, load_golden
from .models import GoldenTask
from .state import AppState, default_out_dir

app = FastAPI(title="aeh-mcp", version="0.1.0", description="Agentic Eval Harness over MCP — offline demo API.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

state = AppState(out_dir=default_out_dir())


class RunRequest(BaseModel):
    task_id: str | None = None
    prompt: str | None = None
    category: str | None = None
    expected: str | None = None


class VerifyRequest(BaseModel):
    run_id: str
    tamper: bool = False


def _record_summary(run_id: str) -> dict:
    trace = state.runs[run_id]
    return {
        "run_id": trace.run_id,
        "task_id": trace.task_id,
        "prompt": trace.prompt,
        "answer": trace.answer,
        "gate": trace.gate,
        "gate_reason": trace.gate_reason,
        "confidence": trace.confidence,
        "n_findings": len(trace.findings),
    }


def _evidence_summary(run_id: str) -> dict | None:
    rec = state.ledger.get(run_id)
    if rec is None:
        return None
    return {
        "this_hash": rec.this_hash,
        "prev_hash": rec.prev_hash,
        "signature": rec.signature,
        "public_key_hex": rec.public_key_hex,
        "timestamp": rec.timestamp,
    }


@app.get("/api/health")
def health() -> dict:
    """Liveness check."""
    return {"status": "ok", "offline": True}


@app.get("/api/provider")
def get_provider() -> dict:
    """The active model provider (mock by default; Gemini/Vertex adapter available)."""
    from .providers import select_provider

    return select_provider().describe()


@app.get("/api/golden")
def get_golden() -> list[dict]:
    """List every golden task (id, prompt, category, adversarial flag)."""
    return [t.to_dict() for t in load_golden()]


@app.post("/api/run")
def post_run(body: RunRequest) -> dict:
    """Run one task (by golden task_id, or an ad-hoc prompt+category) through
    the workflow, seal its evidence, and return the full trace."""
    task = _resolve_run_request(body)
    trace = state.orchestrator.run(task)
    state.record_run(trace)
    out = trace.to_dict()
    out["evidence"] = _evidence_summary(trace.run_id)
    return out


def _resolve_run_request(body: RunRequest) -> GoldenTask:
    if body.task_id:
        task = golden_by_id(body.task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"unknown task_id: {body.task_id}")
        return task
    if body.prompt and body.category:
        return GoldenTask(
            task_id="adhoc",
            prompt=body.prompt,
            category=body.category,
            expected=body.expected or "",
        )
    raise HTTPException(status_code=400, detail="provide task_id, or both prompt and category")


@app.get("/api/runs")
def get_runs() -> list[dict]:
    """List completed runs, most recent first."""
    return [_record_summary(rid) for rid in reversed(state.run_order)]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    """Return the full trace + evidence for one run."""
    trace = state.runs.get(run_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id}")
    out = trace.to_dict()
    out["evidence"] = _evidence_summary(run_id)
    return out


@app.post("/api/eval")
def post_eval() -> dict:
    """Run the entire golden set once, recording every run, and return the
    aggregate eval-suite metrics + gate."""
    tasks = load_golden()
    pairs = []
    for task in tasks:
        trace = state.orchestrator.run(task)
        state.record_run(trace)
        pairs.append((task, trace))
    return summarize(pairs)


@app.post("/api/verify")
def post_verify(body: VerifyRequest) -> dict:
    """Verify a sealed run's evidence three ways (integrity/signature/decision).
    `tamper: true` verifies a mutated COPY instead, to prove rejection."""
    record = state.ledger.get(body.run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {body.run_id}")
    expected_prev = state.ledger.prev_hash_for(body.run_id)
    target = evidence.tamper(record) if body.tamper else record
    result = evidence.verify_record(target, expected_prev_hash=expected_prev)
    result["run_id"] = body.run_id
    result["tampered"] = body.tamper
    return result


@app.post("/mcp")
async def mcp_endpoint(body: dict) -> dict:
    """Minimal JSON-RPC 2.0 MCP-style endpoint: initialize / tools/list / tools/call.

    A `tools/call` for `run_agentic_task` runs the same orchestrator and
    ledger as `/api/run` — the run shows up in `/api/runs` and is verifiable
    exactly like one triggered from the dashboard.
    """
    return mcp.handle_request(body, orchestrator=state.orchestrator, on_trace=state.record_run)
