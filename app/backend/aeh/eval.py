"""Runs the workflow over the golden set and computes aggregate eval metrics."""

from __future__ import annotations

from . import gate
from .golden import load_golden
from .models import GoldenTask, Trace
from .workflow import Orchestrator


def _p95(values: list[int]) -> int:
    """Nearest-rank p95 over a small deterministic sample (no interpolation library needed)."""
    if not values:
        return 0
    ordered = sorted(values)
    idx = max(0, int(round(0.95 * (len(ordered) - 1))))
    return ordered[idx]


def run_eval_suite(orchestrator: Orchestrator | None = None) -> dict:
    """Run every golden task once, compute accuracy/latency/token/tool metrics + gate."""
    orch = orchestrator or Orchestrator()
    tasks = load_golden()
    traces: list[tuple[GoldenTask, Trace]] = [(t, orch.run(t)) for t in tasks]
    result = summarize(traces)
    result["provider"] = orch.provider.describe()
    return result


def summarize(traces: list[tuple[GoldenTask, Trace]]) -> dict:
    """Aggregate a list of (task, trace) pairs into the eval-suite result shape."""
    n = len(traces)
    accuracies = [tr.metrics["accuracy"] for _, tr in traces]
    accuracy = sum(accuracies) / n if n else 0.0

    latencies = [tr.metrics["latency_ms_total"] for _, tr in traces]
    tokens = [tr.metrics["tokens_total"] for _, tr in traces]

    all_tool_calls = [c for _, tr in traces for step in tr.steps for c in step.tool_calls]
    tool_success_rate = (
        sum(1 for c in all_tool_calls if c.success) / len(all_tool_calls) if all_tool_calls else 1.0
    )

    clean = [(t, tr) for t, tr in traces if not t.adversarial]
    adversarial = [(t, tr) for t, tr in traces if t.adversarial]
    blocking_on_clean = sum(
        1 for _, tr in clean for f in tr.findings if f.severity == "blocking"
    )
    adversarial_caught = sum(
        1 for _, tr in adversarial if any(f.severity == "blocking" for f in tr.findings)
    )
    adversarial_catch_rate = (adversarial_caught / len(adversarial)) if adversarial else 1.0

    gate_status, gate_reason = gate.decide_suite(accuracy, blocking_on_clean, adversarial_catch_rate)

    per_task = [
        {
            "task_id": t.task_id,
            "category": t.category,
            "adversarial": t.adversarial,
            "pass": tr.metrics["accuracy"] == 1.0,
            "gate": tr.gate,
            "confidence": tr.confidence,
            "run_id": tr.run_id,
        }
        for t, tr in traces
    ]

    return {
        "n_tasks": n,
        "accuracy": round(accuracy, 4),
        "latency_ms_mean": round(sum(latencies) / n, 1) if n else 0,
        "latency_ms_p95": _p95(latencies),
        "tokens_total": sum(tokens),
        "tokens_mean": round(sum(tokens) / n, 1) if n else 0,
        "tool_call_success_rate": round(tool_success_rate, 4),
        "n_adversarial": len(adversarial),
        "adversarial_catch_rate": round(adversarial_catch_rate, 4),
        "blocking_on_clean": blocking_on_clean,
        "gate": gate_status,
        "gate_reason": gate_reason,
        "per_task": per_task,
    }
