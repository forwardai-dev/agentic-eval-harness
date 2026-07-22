# Technical Spec — Agentic Eval Harness (MCP) `aeh-mcp`

**Runtime contract:** Python 3.11+, FastAPI backend testable via `fastapi.testclient`, single self-contained `index.html` frontend. **Fully offline + deterministic** — no API keys, no network, LLMs replaced by deterministic scripted mocks. IP-clean synthetic data only.

---

## Architecture

**Lead:** a linear multi-agent workflow (planner → executor → critic) wrapped by an orchestrator that records a full trace; the orchestrator is exposed two ways — a REST API for the dashboard and a JSON-RPC MCP endpoint for any MCP client — and every run is sealed into a hash-chained, Ed25519-signed evidence record.

```
                          ┌──────────────────────────────────────┐
 index.html (vanilla JS)  │  FastAPI app (src/aeh/api.py)         │
   dashboard  ───REST────►│  /api/run  /api/runs  /api/eval       │
                          │  /api/verify  /api/golden             │
 any MCP client ──JSON-RPC►  /mcp  (initialize/tools.list/call)   │
                          └───────────────┬──────────────────────┘
                                          ▼
                          Orchestrator (workflow.py)  ── records ──► Trace
                            ├─ PlannerAgent   (mock, deterministic)
                            ├─ ExecutorAgent  (mock; calls Tools)
                            └─ CriticAgent    (mock; scores + findings + confidence)
                                          ▼
                          Eval (eval.py)  ──►  Gate (gate.py, deterministic policy)
                                          ▼
                          Evidence (evidence.py + ledger + Ed25519 signer)
                                          ▼
                          Golden set + runs  (JSON on disk / in-memory)
```

---

## Components

| Module | Responsibility |
|---|---|
| `src/aeh/agents.py` | `PlannerAgent`, `ExecutorAgent`, `CriticAgent` — deterministic mock agents (pure functions of input). Base `AgentResult` dataclass with `output`, `steps`, `tokens`, `latency_ms`, `confidence`, `findings`. |
| `src/aeh/tools.py` | The tool registry the executor calls: `lookup_po`, `compare_amounts`, `lookup_policy`, `classify_request`. Pure, table-driven over synthetic fixtures. Also the tools surfaced via MCP `tools/list`. |
| `src/aeh/workflow.py` | Orchestrator: runs planner → executor → critic, assembles a `Trace` (ordered `TraceStep`s with per-step timing/tokens/tool-calls/confidence). Deterministic latency via a seeded counter, not wall-clock. |
| `src/aeh/golden.py` | Loads the golden set (`fixtures/golden.json`): ~8–10 synthetic enterprise tasks + expected outputs; ≥2 flagged `adversarial: true`. |
| `src/aeh/eval.py` | Runs the workflow over the golden set; computes accuracy (pass^k exact/shape match), mean + p95 latency, total/per-step tokens, tool-call success rate, adversarial catch-rate. |
| `src/aeh/gate.py` | Deterministic policy → `PASS`/`FAIL`: `accuracy ≥ threshold AND no blocking critic findings AND all adversarial tasks caught`. No LLM in the money-path. |
| `src/aeh/evidence.py` | Seals a run into an evidence object; hash-chains + Ed25519-signs (reused from AAH pattern); `verify()` re-checks integrity + signature + decision-replay; `tamper()` helper for the demo. |
| `src/aeh/mcp.py` | Minimal MCP-style JSON-RPC 2.0 handler: `initialize`, `tools/list`, `tools/call`. Maps `run_agentic_task` → orchestrator. |
| `src/aeh/api.py` | FastAPI app wiring all routes + mounting `/mcp`. |
| `index.html` | Single-file dashboard. |
| `README.md` | Exact run + test commands. |

---

## Deterministic-mock strategy (reused from AAH `MockTargetAgent`)

**Lead:** every agent is a pure function of its input, so a task always produces the same trace, metrics, and evidence hash — which is what makes the "replays byte-identical offline" wow-hook true.

- <span class="lbl">Planner</span> rule/keyword-driven decomposition: maps a task's `category` (from the golden fixture) to a fixed ordered step list. No randomness.
- <span class="lbl">Executor</span> resolves each planned step to a `tools.py` call over synthetic fixtures; output is deterministic table lookup. Records the tool name, args, result, success bool.
- <span class="lbl">Critic</span> scores executor output against (a) expected shape/value from the golden fixture and (b) a static policy ruleset (regex for injected instructions à la AAH's `_INJECT_RE`, amount/authority bounds, required-field presence). Emits `findings` (severity + rule id) and a `confidence` derived deterministically from findings, not sampled.
- <span class="lbl">Tokens & latency</span> synthetic but deterministic — token count = a fixed function of input/output length; latency = a seeded per-step constant. Real enough to chart, reproducible enough to hash.
- <span class="lbl">Adversarial handling</span> the critic *ignores* the injected instruction (safe behavior) **and** raises a blocking finding — so the executor's answer may look plausible but the gate still fails. This is the on-camera catch.

---

## Data model

```python
@dataclass(frozen=True)
class GoldenTask:
    task_id: str; prompt: str; category: str
    expected: str; adversarial: bool = False

@dataclass
class ToolCall:
    name: str; args: dict; result: Any; success: bool; latency_ms: int; tokens: int

@dataclass
class TraceStep:
    agent: str            # "planner" | "executor" | "critic"
    input: Any; output: Any
    tool_calls: list[ToolCall]
    tokens: int; latency_ms: int; confidence: float | None

@dataclass
class Finding:
    rule_id: str; severity: str   # "info" | "warn" | "blocking"
    message: str

@dataclass
class Trace:
    run_id: str; task_id: str; prompt: str
    steps: list[TraceStep]
    answer: str; confidence: float
    findings: list[Finding]
    metrics: dict         # latency_ms_total, tokens_total, tool_success_rate
    gate: str             # "PASS" | "FAIL"

@dataclass
class EvidenceRecord:
    run_id: str; payload: dict    # canonical Trace
    prev_hash: str; this_hash: str
    public_key_hex: str; signature: str; timestamp: str
```

Golden set + runs persist as JSON under `fixtures/` and `out/`; the ledger is an append-only JSON list so the hash-chain survives process restart.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/golden` | List golden tasks (id, prompt, category, adversarial flag). |
| `POST` | `/api/run` | Body `{task_id}` or `{prompt, category}` → runs workflow, seals evidence, returns full `Trace` + `run_id`. |
| `GET`  | `/api/runs` | List completed runs (id, task, gate, confidence, timestamp). |
| `GET`  | `/api/runs/{run_id}` | Full `Trace` for one run. |
| `POST` | `/api/eval` | Runs the whole golden set → aggregate metrics + per-task pass/fail + adversarial catch-rate. |
| `POST` | `/api/verify` | Body `{run_id, tamper?: bool}` → `{integrity, signature, decision, verified}`; `tamper:true` mutates a copy to prove rejection. |
| `POST` | `/mcp` | JSON-RPC 2.0: `initialize`, `tools/list`, `tools/call` (`run_agentic_task`). |

All responses JSON. CORS open for `file://` dashboard use. No auth (out of scope).

---

## Frontend layout (`index.html`, Dashboard Clarity Standard)

- **Header:** title + "Offline · no API keys · deterministic" badge + theme note (respects `prefers-color-scheme`, `:root[data-theme]` overrides).
- **Left rail — Run controls:** golden-task picker (adversarial tasks flagged), **Run**, **Run eval suite** buttons.
- **Gate banner:** big **PASS**/**FAIL** with the deciding policy reason as a lead line + keyed bullets.
- **Metrics tiles:** accuracy vs golden, p95 latency, total tokens, tool-call success, adversarial catch-rate.
- **Trace timeline:** planner → executor → critic cards; each card = bold lead (what the agent did) + keyed bullets (tool calls, tokens, latency, confidence); critic findings rendered as `.flag` callouts.
- **MCP panel:** shows the raw `tools/list` + `tools/call` JSON-RPC request/response for the current run (copy-paste `curl` shown).
- **Evidence panel:** **Verify evidence** and **Tamper & re-verify** buttons → integrity/signature/decision result lines.
- Vanilla JS `fetch` only; no external scripts/fonts/CDN. Wide blocks (JSON, trace) scroll inside `overflow-x:auto` containers.

---

## Test plan

**Backend (pytest, `fastapi.testclient` — no live server):**
- `test_agents.py` — planner decomposition is deterministic; executor tool results correct; critic raises blocking finding on injected/malformed input and none on clean input.
- `test_workflow.py` — orchestrator produces a well-formed `Trace`; **determinism test**: two runs of the same task → identical trace + identical evidence `this_hash`.
- `test_eval.py` — accuracy/latency/token/tool-success math on a known golden subset; adversarial catch-rate = 100% on seeded subset.
- `test_gate.py` — policy returns PASS on clean task, FAIL when any adversarial task uncaught / accuracy below threshold / blocking finding present.
- `test_evidence.py` — sign→verify round-trips; **tamper test** mutates a byte and asserts `verify` fails on integrity, signature, and decision-replay (the AAH "caught three ways" regression pattern).
- `test_mcp.py` — `/mcp` answers `initialize` + `tools/list`; `tools/call run_agentic_task` returns the same result shape as `/api/run`; malformed JSON-RPC → proper error object.
- `test_api.py` — every REST route: happy path + one error path each.

**Frontend:**
- Static-load check (dashboard opens with no console errors, no network requests beyond the local API) via `webapp-testing`/Playwright.
- Drive the demo script: run clean task → PASS visible; run adversarial → FAIL + finding visible; verify → VERIFIED; tamper → FAILED. Assert DOM text.
- Lighthouse pass (theme-aware, no layout shift) per `test-audit`.

**Determinism gate (CI-style):** a make target runs a task twice and diffs the evidence hash — must be identical.

---

## Reused AAH / Arbiter patterns

- <span class="lbl">Deterministic scripted mock</span> agents mirror AAH `MockTargetAgent` — pure function of request, `safe` vs `vulnerable`/adversarial paths, same `_INJECT_RE`-style detection in the critic.
- <span class="lbl">Hash-chained signed evidence</span> reuse AAH `audit/ledger.py` (Seal, `prev_hash`/`this_hash`, GENESIS) + `audit/signer.py` (Ed25519) + `core/canonical.py` canonical bytes → the "verify offline / tamper breaks it three ways" property.
- <span class="lbl">Deterministic gate</span> mirrors AAH's no-LLM-in-money-path policy gate (`PASS`/`FAIL` from explicit predicates).
- <span class="lbl">Eval-as-findings</span> critic emits transcript-linked `Finding`s like AAH's eval engine (severity + control ref), not final-answer-only.
- <span class="lbl">Governed workflow shape</span> planner→executor→critic + human-signable gate + immutable audit log mirrors Arbiter's extract → validate → sign-off gateway → audit-log pipeline.

---

## Build order (overnight slice)

1. `agents.py` + `tools.py` + fixtures (golden set) → `test_agents.py` green.
2. `workflow.py` (Trace) → `test_workflow.py` incl. determinism.
3. `eval.py` + `gate.py` → their tests.
4. `evidence.py` (port AAH ledger/signer) → tamper test.
5. `mcp.py` + `api.py` → endpoint tests.
6. `index.html` dashboard → frontend drive + Lighthouse.
7. `README.md` with exact commands.
