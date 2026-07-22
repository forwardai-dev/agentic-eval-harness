"""REST API tests via fastapi.testclient — no live server needed.

Every route: one happy path + one error path.
"""

from __future__ import annotations


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["offline"] is True


def test_get_golden_lists_all_tasks_with_adversarial_flags(client):
    r = client.get("/api/golden")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) >= 8
    assert sum(1 for t in tasks if t["adversarial"]) >= 2


def test_post_run_by_task_id_happy_path(client):
    r = client.post("/api/run", json={"task_id": "gt-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["gate"] == "PASS"
    assert body["evidence"]["this_hash"].startswith("sha256:")
    assert [s["agent"] for s in body["steps"]] == ["planner", "executor", "critic"]


def test_post_run_unknown_task_id_is_404(client):
    r = client.post("/api/run", json={"task_id": "does-not-exist"})
    assert r.status_code == 404


def test_post_run_missing_task_id_and_prompt_is_400(client):
    r = client.post("/api/run", json={})
    assert r.status_code == 400


def test_post_run_adhoc_prompt_and_category(client):
    r = client.post(
        "/api/run",
        json={"prompt": "What is the PTO carryover policy for FY2026?", "category": "policy_lookup"},
    )
    assert r.status_code == 200
    assert "PTO" in r.json()["answer"]


def test_get_runs_lists_completed_runs_most_recent_first(client):
    client.post("/api/run", json={"task_id": "gt-001"})
    client.post("/api/run", json={"task_id": "gt-002"})
    r = client.get("/api/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 2
    assert runs[0]["task_id"] == "gt-002"  # most recent first


def test_get_run_by_id_happy_path(client):
    created = client.post("/api/run", json={"task_id": "gt-001"}).json()
    r = client.get(f"/api/runs/{created['run_id']}")
    assert r.status_code == 200
    assert r.json()["task_id"] == "gt-001"


def test_get_run_by_id_unknown_is_404(client):
    r = client.get("/api/runs/no-such-run")
    assert r.status_code == 404


def test_post_eval_runs_the_whole_golden_set(client):
    r = client.post("/api/eval")
    assert r.status_code == 200
    body = r.json()
    assert body["n_tasks"] >= 8
    assert body["gate"] == "PASS"
    assert body["adversarial_catch_rate"] == 1.0
    # every eval-suite task should now also be visible via /api/runs
    runs = client.get("/api/runs").json()
    assert len(runs) == body["n_tasks"]


def test_post_verify_happy_path(client):
    created = client.post("/api/run", json={"task_id": "gt-001"}).json()
    r = client.post("/api/verify", json={"run_id": created["run_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True


def test_post_verify_with_tamper_flag_fails(client):
    created = client.post("/api/run", json={"task_id": "gt-004"}).json()
    r = client.post("/api/verify", json={"run_id": created["run_id"], "tamper": True})
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is False
    assert body["integrity"] is False


def test_post_verify_unknown_run_id_is_404(client):
    r = client.post("/api/verify", json={"run_id": "no-such-run"})
    assert r.status_code == 404


def test_mcp_initialize(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert r.status_code == 200
    assert r.json()["result"]["serverInfo"]["name"] == "aeh-mcp"


def test_mcp_tools_call_records_a_run_visible_via_rest(client):
    body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "run_agentic_task", "arguments": {"task_id": "gt-003"}},
    }
    r = client.post("/mcp", json=body)
    assert r.status_code == 200
    run_id = r.json()["result"]["trace"]["run_id"]
    follow_up = client.get(f"/api/runs/{run_id}")
    assert follow_up.status_code == 200


def test_mcp_unknown_method_returns_json_rpc_error_with_200_status(client):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 3, "method": "bogus"})
    assert r.status_code == 200
    assert r.json()["error"]["code"] == -32601
