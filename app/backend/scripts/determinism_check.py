#!/usr/bin/env python3
"""CI-style determinism gate: run every golden task twice, in two fresh,
independent process-level objects, and diff the evidence hash. Exits nonzero
(and prints the diff) if anything differs — the same guarantee test_workflow.py
and test_evidence.py check at the unit level, run here end-to-end.

Usage:  python3 scripts/determinism_check.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aeh import evidence  # noqa: E402
from aeh.golden import load_golden  # noqa: E402
from aeh.workflow import Orchestrator  # noqa: E402


def main() -> int:
    tasks = load_golden()
    mismatches = []
    for task in tasks:
        trace_a = Orchestrator().run(task)
        trace_b = Orchestrator().run(task)

        if trace_a.to_dict() != trace_b.to_dict():
            mismatches.append((task.task_id, "trace mismatch"))
            continue

        ledger_a, ledger_b = evidence.Ledger(), evidence.Ledger()
        seal_a = ledger_a.append(trace_a.run_id, trace_a.to_dict())
        seal_b = ledger_b.append(trace_b.run_id, trace_b.to_dict())

        if seal_a.this_hash != seal_b.this_hash:
            mismatches.append((task.task_id, f"evidence hash mismatch: {seal_a.this_hash} != {seal_b.this_hash}"))
            continue

        print(f"OK   {task.task_id:8s} run_id={trace_a.run_id}  evidence={seal_a.this_hash}")

    if mismatches:
        print("\nDETERMINISM CHECK FAILED:")
        for task_id, reason in mismatches:
            print(f"  {task_id}: {reason}")
        return 1

    print(f"\nDETERMINISM CHECK PASSED — {len(tasks)}/{len(tasks)} golden tasks byte-identical across two runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
