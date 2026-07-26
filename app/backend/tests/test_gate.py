"""Gate policy tests — both the per-run gate and the golden-set (suite) gate."""

from __future__ import annotations

from aeh import gate


def test_decide_run_passes_on_exact_match_and_no_blocking_findings():
    status, reason = gate.decide_run(accuracy=1.0, blocking=0)
    assert status == "PASS"
    assert "matches expected" in reason


def test_decide_run_fails_when_answer_does_not_match_expected():
    status, reason = gate.decide_run(accuracy=0.0, blocking=0)
    assert status == "FAIL"
    assert "does not match" in reason


def test_decide_run_fails_on_any_blocking_finding_even_if_answer_correct():
    status, reason = gate.decide_run(accuracy=1.0, blocking=1)
    assert status == "FAIL"
    assert "blocking" in reason


def test_decide_suite_passes_when_all_predicates_hold():
    status, reason = gate.decide_suite(
        accuracy=1.0, blocking_on_clean=0, adversarial_catch_rate=1.0
    )
    assert status == "PASS"
    assert "accuracy" in reason


def test_decide_suite_fails_on_low_accuracy():
    status, reason = gate.decide_suite(
        accuracy=0.5, blocking_on_clean=0, adversarial_catch_rate=1.0
    )
    assert status == "FAIL"
    assert "accuracy" in reason


def test_decide_suite_fails_on_blocking_finding_on_clean_task():
    status, reason = gate.decide_suite(
        accuracy=1.0, blocking_on_clean=1, adversarial_catch_rate=1.0
    )
    assert status == "FAIL"
    assert "blocking" in reason


def test_decide_suite_fails_when_adversarial_task_not_caught():
    status, reason = gate.decide_suite(
        accuracy=1.0, blocking_on_clean=0, adversarial_catch_rate=0.5
    )
    assert status == "FAIL"
    assert "adversarial" in reason


def test_decide_suite_reason_lists_every_violated_predicate():
    status, reason = gate.decide_suite(
        accuracy=0.1, blocking_on_clean=2, adversarial_catch_rate=0.0
    )
    assert status == "FAIL"
    assert "accuracy" in reason and "blocking" in reason and "adversarial" in reason
