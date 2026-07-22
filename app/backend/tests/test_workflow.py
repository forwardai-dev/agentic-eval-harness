"""Orchestrator tests: well-formed Trace, and the determinism guarantee."""

from __future__ import annotations

from aeh.golden import golden_by_id, load_golden
from aeh.workflow import Orchestrator


def test_orchestrator_produces_well_formed_trace():
    task = golden_by_id("gt-001")
    trace = Orchestrator().run(task)
    assert [s.agent for s in trace.steps] == ["planner", "executor", "critic"]
    assert trace.answer == task.expected
    assert trace.gate in ("PASS", "FAIL")
    assert trace.gate == "PASS"
    assert trace.metrics["latency_ms_total"] > 0
    assert trace.metrics["tokens_total"] > 0
    assert 0.0 <= trace.confidence <= 1.0


def test_orchestrator_two_runs_of_same_task_are_byte_identical():
    task = golden_by_id("gt-001")
    t1 = Orchestrator().run(task)
    t2 = Orchestrator().run(task)
    assert t1.to_dict() == t2.to_dict()
    assert t1.run_id == t2.run_id


def test_orchestrator_clean_task_passes_gate():
    task = golden_by_id("gt-001")
    trace = Orchestrator().run(task)
    assert trace.gate == "PASS"
    assert trace.findings == []


def test_orchestrator_adversarial_task_fails_gate_when_caught():
    task = golden_by_id("gt-004")
    trace = Orchestrator().run(task)
    assert trace.gate == "FAIL"
    assert any(f.severity == "blocking" for f in trace.findings)


def test_orchestrator_runs_the_entire_golden_set_without_error():
    orch = Orchestrator()
    for task in load_golden():
        trace = orch.run(task)
        assert trace.gate in ("PASS", "FAIL")
        assert trace.answer  # never empty
