"""In-process app state: the live orchestrator, the growing evidence ledger,
and the run history — plus best-effort JSON persistence under `out/` so runs
survive a process restart. Persistence never blocks or fails a run."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .evidence import Ledger
from .models import Trace
from .workflow import Orchestrator


class AppState:
    """Holds everything one running server instance needs across requests."""

    def __init__(self, out_dir: Path | None = None) -> None:
        self.orchestrator = Orchestrator()
        self.ledger = Ledger()
        self.runs: dict[str, Trace] = {}
        self.run_order: list[str] = []
        self.out_dir = out_dir

    def record_run(self, trace: Trace) -> None:
        """Store a completed run, chain+sign its evidence, and persist best-effort.

        Runs are content-addressed (`run_id` is a hash of task_id+prompt), so
        re-running the identical task is idempotent: it does not grow the
        ledger with a duplicate entry, it just reconfirms the same sealed
        evidence — the "run it again, get the identical record" property.
        """
        already_sealed = trace.run_id in self.run_order
        self.runs[trace.run_id] = trace
        if not already_sealed:
            self.run_order.append(trace.run_id)
            self.ledger.append(trace.run_id, trace.to_dict())
        if self.out_dir is not None:
            self._persist(trace)

    def reset(self) -> None:
        """Wipe all in-memory state — used between tests / demo resets."""
        self.orchestrator = Orchestrator()
        self.ledger = Ledger()
        self.runs = {}
        self.run_order = []

    def _persist(self, trace: Trace) -> None:
        try:
            runs_dir = self.out_dir / "runs"  # type: ignore[operator]
            runs_dir.mkdir(parents=True, exist_ok=True)
            (runs_dir / f"{trace.run_id}.json").write_text(
                json.dumps(trace.to_dict(), indent=2), encoding="utf-8"
            )
            ledger_path = self.out_dir / "ledger.json"  # type: ignore[operator]
            ledger_path.write_text(
                json.dumps([r.to_dict() for r in self.ledger.list_records()], indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass  # best-effort; disk I/O never breaks the demo


def default_out_dir() -> Path | None:
    """Resolve the persistence dir from AEH_OUT_DIR ('' or 'none' disables it)."""
    raw = os.environ.get("AEH_OUT_DIR", "out")
    if raw.strip().lower() in ("", "none"):
        return None
    return Path(raw)
