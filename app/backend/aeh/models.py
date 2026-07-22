"""Data model for the eval harness: golden tasks, traces, findings, evidence.

All dataclasses are plain-data and JSON-round-trippable (`to_dict`), which is
what lets the API, the MCP handler, and the evidence sealer share one shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GoldenTask:
    """One synthetic enterprise task in the golden set."""

    task_id: str
    prompt: str
    category: str
    expected: str
    adversarial: bool = False
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "prompt": self.prompt,
            "category": self.category,
            "expected": self.expected,
            "adversarial": self.adversarial,
            "context": self.context,
        }


@dataclass
class ToolCall:
    """One tool invocation made by the executor."""

    name: str
    args: dict
    result: Any
    success: bool
    latency_ms: int
    tokens: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "result": self.result,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
        }


@dataclass
class Finding:
    """A critic-raised finding: a rule id, severity, and a human message."""

    rule_id: str
    severity: str  # "info" | "warn" | "blocking"
    message: str

    def to_dict(self) -> dict:
        return {"rule_id": self.rule_id, "severity": self.severity, "message": self.message}


@dataclass
class TraceStep:
    """One agent's contribution to a trace: input, output, tool calls, cost."""

    agent: str  # "planner" | "executor" | "critic"
    input: Any
    output: Any
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "input": self.input,
            "output": self.output,
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "tokens": self.tokens,
            "latency_ms": self.latency_ms,
            "confidence": self.confidence,
        }


@dataclass
class Trace:
    """The full record of one workflow run: every step, the answer, the gate."""

    run_id: str
    task_id: str
    prompt: str
    steps: list[TraceStep]
    answer: str
    confidence: float
    findings: list[Finding]
    metrics: dict
    gate: str  # "PASS" | "FAIL"
    gate_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "steps": [s.to_dict() for s in self.steps],
            "answer": self.answer,
            "confidence": self.confidence,
            "findings": [f.to_dict() for f in self.findings],
            "metrics": self.metrics,
            "gate": self.gate,
            "gate_reason": self.gate_reason,
        }
