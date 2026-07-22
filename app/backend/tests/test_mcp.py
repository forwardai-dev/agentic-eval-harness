"""MCP JSON-RPC 2.0 handler: initialize, tools/list, tools/call, malformed input."""

from __future__ import annotations

from aeh import mcp
from aeh.workflow import Orchestrator


def test_initialize_returns_protocol_and_server_info():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert "error" not in resp
    assert resp["result"]["serverInfo"]["name"] == "aeh-mcp"
    assert "protocolVersion" in resp["result"]


def test_tools_list_exposes_run_agentic_task():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "run_agentic_task" in names


def test_tools_call_by_task_id_matches_rest_api_shape():
    body = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "run_agentic_task", "arguments": {"task_id": "gt-001"}},
    }
    resp = mcp.handle_request(body, orchestrator=Orchestrator())
    assert "error" not in resp
    trace = resp["result"]["trace"]
    assert trace["task_id"] == "gt-001"
    assert trace["gate"] == "PASS"
    assert resp["result"]["isError"] is False
    assert [s["agent"] for s in trace["steps"]] == ["planner", "executor", "critic"]


def test_tools_call_adversarial_task_marks_is_error_true():
    body = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "run_agentic_task", "arguments": {"task_id": "gt-004"}},
    }
    resp = mcp.handle_request(body, orchestrator=Orchestrator())
    assert resp["result"]["isError"] is True
    assert resp["result"]["trace"]["gate"] == "FAIL"


def test_tools_call_with_adhoc_prompt_and_category():
    body = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "run_agentic_task",
            "arguments": {
                "prompt": "What is the PTO carryover policy for FY2026?",
                "category": "policy_lookup",
            },
        },
    }
    resp = mcp.handle_request(body, orchestrator=Orchestrator())
    assert "error" not in resp
    assert "PTO" in resp["result"]["trace"]["answer"]


def test_tools_call_unknown_task_id_returns_json_rpc_error():
    body = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {"name": "run_agentic_task", "arguments": {"task_id": "gt-does-not-exist"}},
    }
    resp = mcp.handle_request(body)
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_unknown_method_returns_json_rpc_error():
    resp = mcp.handle_request({"jsonrpc": "2.0", "id": 7, "method": "not_a_real_method"})
    assert resp["error"]["code"] == -32601


def test_malformed_body_not_a_dict_returns_json_rpc_error():
    resp = mcp.handle_request(["not", "an", "object"])
    assert "error" in resp
    assert resp["id"] is None


def test_tools_call_missing_name_returns_error():
    body = {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"arguments": {}}}
    resp = mcp.handle_request(body)
    assert "error" in resp


def test_on_trace_callback_is_invoked_for_a_real_run():
    seen = []
    body = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {"name": "run_agentic_task", "arguments": {"task_id": "gt-001"}},
    }
    mcp.handle_request(body, orchestrator=Orchestrator(), on_trace=seen.append)
    assert len(seen) == 1
    assert seen[0].task_id == "gt-001"
