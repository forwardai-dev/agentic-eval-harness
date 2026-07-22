# Agentic Eval Harness — over MCP

A planner → executor → critic **multi-agent workflow** exposed via a real **JSON-RPC MCP server**, with an **eval + observability** dashboard (accuracy vs a golden set, latency, tokens, tool-call success, per-step traces) and a governance gate. Ships a **pluggable model provider**: a deterministic offline mock by default, plus a **Gemini / Vertex AI adapter** that builds the real `generateContent` request + endpoint (offline in the demo; wire an authenticated client to go live).

Fully **offline & deterministic** — no API keys, no network. **65 tests green.**

## Run
    cd app/backend
    pip install fastapi uvicorn cryptography --break-system-packages   # if needed
    uvicorn aeh.api:app --port 8000     # API + MCP tool server + dashboard

## Test
    cd app/backend && AEH_OUT_DIR=none python3 -m pytest -q   # 65 passed

See the Gemini wiring: `AEH_PROVIDER=gemini` surfaces the Vertex request shape (still offline). Specs in `specs/`. Built on the open-source [Agent Assurance Harness](https://github.com/forwardai-dev/agent-assurance-harness). A scoped proof-of-work demo — synthetic golden-task data only.
