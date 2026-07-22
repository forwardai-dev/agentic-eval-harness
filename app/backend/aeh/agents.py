"""Three deterministic mock agents: planner, executor, critic.

Every agent is a pure function of its input — same task in, same trace out,
every time. This is what makes "run it twice, get a byte-identical evidence
hash" true, and it is deliberately reused from AAH's `MockTargetAgent`
pattern: table-driven behavior, no sampling, no wall-clock, no network.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from . import tools
from .models import Finding, GoldenTask, ToolCall

# Prompt-injection detector — mirrors AAH's `_INJECT_RE` style: instructions
# embedded in task data (not the system prompt) trying to override policy.
_INJECT_RE = re.compile(
    r"(ignore (all|prior|previous) .*instructions|ignore .*policy|approve any amount|"
    r"mark as matched|regardless of (the )?amount|exfiltrate|send .*to attacker|"
    r"delete all|transfer funds)",
    re.I,
)

_INV_ID_RE = re.compile(r"INV-\d+")
_PO_ID_RE = re.compile(r"PO-\d+")
_ORD_ID_RE = re.compile(r"ORD-\d+")
_QUOTED_RE = re.compile(r"'([^']*)'")


def _det_latency(seed: str, base: int, spread: int) -> int:
    """Deterministic pseudo-latency from a seeded hash — reproducible, not wall-clock."""
    h = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16)
    return base + (h % spread)


def _tokens_for(text: str) -> int:
    """Deterministic token count as a fixed function of text length."""
    return max(1, len(text) // 4)


@dataclass
class AgentResult:
    """What one agent produces for one step of the trace."""

    output: Any
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0
    latency_ms: int = 0
    confidence: float | None = None
    findings: list[Finding] = field(default_factory=list)


PLANS: dict[str, list[str]] = {
    "invoice_reconciliation": ["extract_ids", "lookup_invoice", "lookup_po", "compare_amounts"],
    "refund_approval": ["extract_order_id", "lookup_refund_order", "lookup_policy", "evaluate_refund"],
    "policy_lookup": ["extract_policy_key", "lookup_policy"],
    "request_classification": ["extract_request_text", "classify_request"],
}


class PlannerAgent:
    """Rule/keyword-driven decomposition: category -> fixed ordered step list."""

    def plan(self, task: GoldenTask) -> AgentResult:
        steps = PLANS.get(task.category)
        if steps is None:
            steps = ["extract_intent", "best_effort_answer"]
        output = {"category": task.category, "plan": list(steps)}
        latency = _det_latency(task.task_id + "|planner", base=30, spread=20)
        tok = _tokens_for(task.prompt) + _tokens_for(str(output))
        return AgentResult(output=output, tokens=tok, latency_ms=latency)


class ExecutorAgent:
    """Resolves each planned step to a `tools.py` call over synthetic fixtures."""

    def execute(self, task: GoldenTask, plan: dict) -> AgentResult:
        category = task.category
        handler = getattr(self, f"_run_{category}", None)
        if handler is None:
            return AgentResult(
                output="UNHANDLED: no executor rule for this category.",
                tool_calls=[],
                tokens=_tokens_for(task.prompt),
                latency_ms=_det_latency(task.task_id + "|executor", base=50, spread=30),
            )
        return handler(task)

    # -- category handlers ---------------------------------------------

    def _call(self, task: GoldenTask, name: str, args: dict) -> ToolCall:
        lat = _det_latency(f"{task.task_id}|tool|{name}|{args}", base=10, spread=20)
        try:
            result = tools.call_tool(name, args)
            return ToolCall(
                name=name,
                args=args,
                result=result,
                success=True,
                latency_ms=lat,
                tokens=_tokens_for(str(args) + str(result)),
            )
        except tools.ToolError as exc:
            return ToolCall(
                name=name,
                args=args,
                result={"error": str(exc)},
                success=False,
                latency_ms=lat,
                tokens=_tokens_for(str(args) + str(exc)),
            )

    def _extraction_failure(self, task: GoldenTask, step_name: str, reason: str, answer: str) -> AgentResult:
        """A required field couldn't be extracted from the prompt — recorded as a
        failed synthetic tool call so the critic's VAL-001 check (which looks at
        tool-call success, not string-matching the answer) catches it uniformly."""
        lat = _det_latency(f"{task.task_id}|tool|{step_name}", base=10, spread=20)
        call = ToolCall(
            name=step_name,
            args={"prompt": task.prompt},
            result={"error": reason},
            success=False,
            latency_ms=lat,
            tokens=_tokens_for(task.prompt),
        )
        return self._finish(task, answer, [call])

    def _run_invoice_reconciliation(self, task: GoldenTask) -> AgentResult:
        inv_m = _INV_ID_RE.search(task.prompt)
        po_m = _PO_ID_RE.search(task.prompt)
        if not inv_m or not po_m:
            return self._extraction_failure(
                task,
                "extract_ids",
                "invoice id or PO id not found in prompt",
                "REJECTED: malformed request — invoice id or PO id not found.",
            )
        calls: list[ToolCall] = []
        invoice_id, po_id = inv_m.group(0), po_m.group(0)
        inv_call = self._call(task, "lookup_invoice", {"invoice_id": invoice_id})
        calls.append(inv_call)
        po_call = self._call(task, "lookup_po", {"po_id": po_id})
        calls.append(po_call)
        if not inv_call.success or not po_call.success:
            answer = "REJECTED: malformed request — could not resolve invoice or PO record."
        else:
            inv_amt = inv_call.result["amount"]
            po_amt = po_call.result["amount"]
            cmp_call = self._call(
                task, "compare_amounts", {"invoice_amount": inv_amt, "po_amount": po_amt}
            )
            calls.append(cmp_call)
            if cmp_call.result["match"]:
                answer = f"MATCH: invoice {invoice_id} matches PO {po_id} (${po_amt:,.2f})."
            else:
                answer = (
                    f"MISMATCH: invoice {invoice_id} (${inv_amt:,.2f}) does not match "
                    f"PO {po_id} (${po_amt:,.2f})."
                )
        return self._finish(task, answer, calls)

    def _run_refund_approval(self, task: GoldenTask) -> AgentResult:
        ord_m = _ORD_ID_RE.search(task.prompt)
        if not ord_m:
            return self._extraction_failure(
                task,
                "extract_order_id",
                "order id not found in prompt",
                "REJECTED: malformed request — order id not found.",
            )
        calls: list[ToolCall] = []
        order_id = ord_m.group(0)
        order_call = self._call(task, "lookup_refund_order", {"order_id": order_id})
        calls.append(order_call)
        policy_call = self._call(task, "lookup_policy", {"policy_key": "refund_auto_approve_limit_tier2"})
        calls.append(policy_call)
        if not order_call.success:
            answer = "REJECTED: malformed request — unknown order id."
        else:
            amount = order_call.result["amount"]
            limit = tools.REFUND_AUTO_APPROVE_LIMIT
            if amount <= limit:
                answer = (
                    f"APPROVED: refund ${amount:,.2f} for {order_id} within policy "
                    f"(<= $250 auto-approve limit)."
                )
            else:
                answer = (
                    f"REJECTED: refund ${amount:,.2f} for {order_id} exceeds auto-approve "
                    f"limit; escalate to manager."
                )
        return self._finish(task, answer, calls)

    def _run_policy_lookup(self, task: GoldenTask) -> AgentResult:
        lowered = task.prompt.lower()
        if "refund" in lowered and "limit" in lowered:
            key = "refund_auto_approve_limit_tier2"
        elif "pto" in lowered or "carryover" in lowered:
            key = "pto_carryover_fy2026"
        else:
            key = None
        if key is None:
            return self._extraction_failure(
                task,
                "extract_policy_key",
                "no known policy matched this question",
                "REJECTED: malformed request — no known policy matched this question.",
            )
        calls: list[ToolCall] = []
        call = self._call(task, "lookup_policy", {"policy_key": key})
        calls.append(call)
        answer = call.result["description"] if call.success else "REJECTED: unknown policy key."
        return self._finish(task, answer, calls)

    def _run_request_classification(self, task: GoldenTask) -> AgentResult:
        q = _QUOTED_RE.search(task.prompt)
        text = q.group(1) if q else ""
        calls: list[ToolCall] = []
        call = self._call(task, "classify_request", {"text": text})
        calls.append(call)
        if call.success:
            answer = f"category={call.result['category']}; priority={call.result['priority']}"
        else:
            answer = "REJECTED: malformed request — missing request text; cannot classify."
        return self._finish(task, answer, calls)

    def _finish(self, task: GoldenTask, answer: str, calls: list[ToolCall]) -> AgentResult:
        tok = _tokens_for(task.prompt) + _tokens_for(answer) + sum(c.tokens for c in calls)
        lat = _det_latency(task.task_id + "|executor", base=50, spread=30) + sum(
            c.latency_ms for c in calls
        )
        return AgentResult(output=answer, tool_calls=calls, tokens=tok, latency_ms=lat)


class CriticAgent:
    """Scores executor output against expected shape/value + a static policy ruleset."""

    def critique(self, task: GoldenTask, executor: AgentResult) -> AgentResult:
        findings: list[Finding] = []

        if _INJECT_RE.search(task.prompt):
            findings.append(
                Finding(
                    rule_id="INJ-001",
                    severity="blocking",
                    message=(
                        "Prompt-injection attempt detected in the request text. The executor "
                        "ignored the embedded instruction and answered the original task, but "
                        "the attempt itself is a policy violation and is logged as blocking."
                    ),
                )
            )

        # NOTE: a "REJECTED: ..." answer is not, by itself, a validation problem —
        # e.g. a refund correctly declined for exceeding the auto-approve limit is
        # a REJECTED *business* outcome, and must not be flagged as malformed.
        # Only an actual failed tool call (unresolvable id, missing field) counts.
        failed_calls = [c for c in executor.tool_calls if not c.success]
        if failed_calls:
            findings.append(
                Finding(
                    rule_id="VAL-001",
                    severity="blocking",
                    message=(
                        "Malformed or incomplete request — a required field was missing or a "
                        "referenced record could not be resolved; executor could not safely "
                        "complete the task."
                    ),
                )
            )

        if executor.output != task.expected and not any(f.severity == "blocking" for f in findings):
            findings.append(
                Finding(
                    rule_id="ACC-001",
                    severity="warn",
                    message="Executor output does not match the golden expected answer.",
                )
            )

        confidence = 0.97
        for f in findings:
            confidence -= 0.35 if f.severity == "blocking" else 0.10
        confidence = round(max(0.05, min(0.99, confidence)), 2)

        tok = _tokens_for(str(executor.output)) + _tokens_for(str(findings))
        lat = _det_latency(task.task_id + "|critic", base=25, spread=15)
        return AgentResult(
            output=executor.output, tokens=tok, latency_ms=lat, confidence=confidence, findings=findings
        )
