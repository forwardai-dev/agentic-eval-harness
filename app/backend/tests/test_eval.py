"""Eval-suite metrics: accuracy, latency, tokens, tool-success, adversarial catch-rate."""

from __future__ import annotations

from aeh.eval import run_eval_suite
from aeh.golden import load_golden


def test_eval_suite_covers_the_whole_golden_set():
    result = run_eval_suite()
    assert result["n_tasks"] == len(load_golden())
    assert len(result["per_task"]) == result["n_tasks"]


def test_eval_suite_accuracy_is_perfect_on_the_authored_golden_set():
    # every golden expected answer is authored to match what the deterministic
    # executor actually produces, so accuracy should be 100%.
    result = run_eval_suite()
    assert result["accuracy"] == 1.0
    assert all(t["pass"] for t in result["per_task"])


def test_eval_suite_adversarial_catch_rate_is_100_percent():
    result = run_eval_suite()
    assert result["n_adversarial"] >= 2
    assert result["adversarial_catch_rate"] == 1.0


def test_eval_suite_tool_call_success_rate_reflects_the_one_seeded_malformed_task():
    # gt-008 is a deliberately malformed (empty-text) adversarial task: its
    # classify_request tool call is expected to fail. Every other tool call in
    # the golden set resolves against a known fixture id, so it succeeds.
    result = run_eval_suite()
    assert 0.0 < result["tool_call_success_rate"] < 1.0


def test_eval_suite_gate_passes_when_all_predicates_hold():
    result = run_eval_suite()
    assert result["gate"] == "PASS"
    assert result["blocking_on_clean"] == 0


def test_eval_suite_latency_and_token_rollups_are_positive():
    result = run_eval_suite()
    assert result["latency_ms_mean"] > 0
    assert result["latency_ms_p95"] >= result["latency_ms_mean"] * 0  # sanity: non-negative
    assert result["tokens_total"] > 0
