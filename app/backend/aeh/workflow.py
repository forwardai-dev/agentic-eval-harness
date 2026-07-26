"""Orchestrator: runs planner -> executor -> critic and assembles a Trace.

Deterministic end to end: run the same task twice, get the identical Trace
(and therefore the identical evidence hash once sealed). Latency is a seeded
function of the task, never wall-clock.
"""

from __future__ import annotations

import hashlib

from . import gate
from .agents import CriticAgent, ExecutorAgent, PlannerAgent
from .models import GoldenTask, Trace, TraceStep


def _run_id_for(task: GoldenTask) -> str:
    """Deterministic run id — a content hash of the task, not a random uuid.

    This is what makes repeated runs of the same task produce the identical
    evidence hash (the demo's "byte-identical replay" proof point).
    """
    h = hashlib.sha256(f"{task.task_id}|{task.prompt}".encode("utf-8")).hexdigest()[:16]
    return f"run-{task.task_id}-{h}"


class Orchestrator:
    """Runs the planner -> executor -> critic workflow and records the Trace."""

    def __init__(self, provider=None) -> None:
        from .providers import select_provider

        # The model backend is a pluggable seam (mock by default; Gemini/Vertex adapter
        # available). It does NOT enter the hashed trace/evidence, so runs stay byte-identical.
        self.provider = provider or select_provider()
        self.planner = PlannerAgent()
        self.executor = ExecutorAgent()
        self.critic = CriticAgent()

    def run(self, task: GoldenTask) -> Trace:
        """Run one task through the full workflow and return its sealed-ready Trace."""
        plan_result = self.planner.plan(task)
        plan_step = TraceStep(
            agent="planner",
            input={
                "task_id": task.task_id,
                "prompt": task.prompt,
                "category": task.category,
            },
            output=plan_result.output,
            tool_calls=[],
            tokens=plan_result.tokens,
            latency_ms=plan_result.latency_ms,
            confidence=None,
        )

        exec_result = self.executor.execute(task, plan_result.output)
        exec_step = TraceStep(
            agent="executor",
            input=plan_result.output,
            output=exec_result.output,
            tool_calls=exec_result.tool_calls,
            tokens=exec_result.tokens,
            latency_ms=exec_result.latency_ms,
            confidence=None,
        )

        critic_result = self.critic.critique(task, exec_result)
        critic_step = TraceStep(
            agent="critic",
            input=exec_result.output,
            output=critic_result.output,
            tool_calls=[],
            tokens=critic_result.tokens,
            latency_ms=critic_result.latency_ms,
            confidence=critic_result.confidence,
        )

        steps = [plan_step, exec_step, critic_step]
        latency_total = sum(s.latency_ms for s in steps)
        tokens_total = sum(s.tokens for s in steps)
        tool_calls = exec_step.tool_calls
        tool_success_rate = (
            sum(1 for c in tool_calls if c.success) / len(tool_calls)
            if tool_calls
            else 1.0
        )

        accuracy = 1.0 if critic_result.output == task.expected else 0.0
        blocking = sum(1 for f in critic_result.findings if f.severity == "blocking")
        gate_status, gate_reason = gate.decide_run(accuracy, blocking)

        metrics = {
            "latency_ms_total": latency_total,
            "tokens_total": tokens_total,
            "tool_success_rate": round(tool_success_rate, 4),
            "accuracy": accuracy,
            "adversarial": task.adversarial,
        }

        return Trace(
            run_id=_run_id_for(task),
            task_id=task.task_id,
            prompt=task.prompt,
            steps=steps,
            answer=critic_result.output,
            confidence=critic_result.confidence,
            findings=critic_result.findings,
            metrics=metrics,
            gate=gate_status,
            gate_reason=gate_reason,
        )
