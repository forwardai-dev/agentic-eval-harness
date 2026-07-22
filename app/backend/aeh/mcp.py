"""Minimal MCP-style JSON-RPC 2.0 handler: initialize, tools/list, tools/call.

A protocol-shaped, client-callable JSON-RPC-over-HTTP subset (full stdio/SSE
transport negotiation is out of scope per the functional spec). Any MCP
client that can POST JSON-RPC 2.0 can call `run_agentic_task` here.
"""

from __future__ import annotations

from typing import Any, Callable

from .golden import golden_by_id
from .models import GoldenTask, Trace
from .workflow import Orchestrator

MCP_PROTOCOL_VERSION = "2024-11-05"

TOOL_DEF: dict[str, Any] = {
    "name": "run_agentic_task",
    "description": (
        "Run an enterprise task through the planner -> executor -> critic workflow "
        "and return the full trace, findings, and governance gate decision."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "A golden-set task id, e.g. gt-001"},
            "prompt": {"type": "string", "description": "Free-text prompt (with category, if task_id omitted)"},
            "category": {
                "type": "string",
                "description": (
                    "invoice_reconciliation | refund_approval | policy_lookup | "
                    "request_classification"
                ),
            },
        },
        "required": [],
    },
}


class MCPError(Exception):
    """A JSON-RPC error with a code + message."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _resolve_task(args: dict) -> GoldenTask:
    task_id = args.get("task_id")
    if task_id:
        task = golden_by_id(task_id)
        if task is None:
            raise MCPError(-32602, f"unknown task_id: {task_id}")
        return task
    prompt, category = args.get("prompt"), args.get("category")
    if not prompt or not category:
        raise MCPError(-32602, "invalid params: provide task_id, or both prompt and category")
    return GoldenTask(task_id="adhoc", prompt=prompt, category=category, expected=args.get("expected", ""))


def handle_request(
    body: Any,
    orchestrator: Orchestrator | None = None,
    on_trace: Callable[[Trace], None] | None = None,
) -> dict:
    """Handle one JSON-RPC 2.0 request dict and return the response dict.

    `on_trace`, if given, is called with the resulting `Trace` whenever
    `tools/call` actually ran the workflow (lets the caller record/seal it
    into the same evidence ledger a REST `/api/run` would use)."""
    if not isinstance(body, dict):
        return {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "invalid request: expected a JSON object"},
        }

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}

    try:
        if method == "initialize":
            result: Any = {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {"name": "aeh-mcp", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            }
        elif method == "tools/list":
            result = {"tools": [TOOL_DEF]}
        elif method == "tools/call":
            name = params.get("name")
            if name != "run_agentic_task":
                raise MCPError(-32601, f"unknown tool: {name}")
            args = params.get("arguments") or {}
            task = _resolve_task(args)
            orch = orchestrator or Orchestrator()
            trace = orch.run(task)
            if on_trace is not None:
                on_trace(trace)
            result = {
                "content": [{"type": "text", "text": trace.answer}],
                "isError": trace.gate == "FAIL",
                "trace": trace.to_dict(),
            }
        else:
            raise MCPError(-32601, f"method not found: {method}")
    except MCPError as exc:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # never leak a raw traceback to a client
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32603, "message": f"internal error: {exc}"}}

    return {"jsonrpc": "2.0", "id": req_id, "result": result}
