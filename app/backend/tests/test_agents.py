"""Agent-level unit tests: deterministic planner, correct executor tool use,
critic blocking findings on injected/malformed input, none on clean input."""

from __future__ import annotations

from aeh.agents import CriticAgent, ExecutorAgent, PlannerAgent
from aeh.golden import golden_by_id


def test_planner_decomposition_is_deterministic_and_category_specific():
    planner = PlannerAgent()
    task = golden_by_id("gt-001")
    r1 = planner.plan(task)
    r2 = planner.plan(task)
    assert r1.output == r2.output
    assert r1.output["category"] == "invoice_reconciliation"
    assert r1.output["plan"] == ["extract_ids", "lookup_invoice", "lookup_po", "compare_amounts"]


def test_planner_plan_differs_by_category():
    planner = PlannerAgent()
    refund_plan = planner.plan(golden_by_id("gt-003")).output["plan"]
    policy_plan = planner.plan(golden_by_id("gt-005")).output["plan"]
    assert refund_plan != policy_plan


def test_executor_tool_results_correct_on_matching_invoice():
    task = golden_by_id("gt-001")
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    assert exec_result.output == task.expected
    tool_names = [c.name for c in exec_result.tool_calls]
    assert tool_names == ["lookup_invoice", "lookup_po", "compare_amounts"]
    assert all(c.success for c in exec_result.tool_calls)
    compare_call = exec_result.tool_calls[-1]
    assert compare_call.result["match"] is True


def test_executor_tool_results_correct_on_mismatched_invoice():
    task = golden_by_id("gt-002")
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    assert exec_result.output == task.expected
    assert exec_result.tool_calls[-1].result["match"] is False


def test_executor_refund_approval_within_limit():
    task = golden_by_id("gt-003")
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    assert exec_result.output.startswith("APPROVED")
    assert exec_result.output == task.expected


def test_critic_raises_no_findings_on_clean_task():
    task = golden_by_id("gt-001")
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    critic_result = CriticAgent().critique(task, exec_result)
    assert critic_result.findings == []
    assert critic_result.confidence >= 0.9


def test_critic_raises_blocking_finding_on_injected_instruction():
    task = golden_by_id("gt-004")  # adversarial: injected "approve any amount"
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    critic_result = CriticAgent().critique(task, exec_result)
    blocking = [f for f in critic_result.findings if f.severity == "blocking"]
    assert blocking, "expected at least one blocking finding for injected instruction"
    assert any(f.rule_id == "INJ-001" for f in blocking)
    # the safe executor still gives the correct (policy-respecting) answer
    assert exec_result.output == task.expected
    assert critic_result.confidence < 0.9


def test_critic_raises_blocking_finding_on_malformed_input():
    task = golden_by_id("gt-008")  # adversarial: empty request text
    planner_out = PlannerAgent().plan(task).output
    exec_result = ExecutorAgent().execute(task, planner_out)
    critic_result = CriticAgent().critique(task, exec_result)
    blocking = [f for f in critic_result.findings if f.severity == "blocking"]
    assert any(f.rule_id == "VAL-001" for f in blocking)
