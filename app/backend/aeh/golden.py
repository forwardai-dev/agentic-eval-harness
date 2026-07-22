"""Loads the golden set: ~10 synthetic enterprise tasks with expected answers."""

from __future__ import annotations

import json
from pathlib import Path

from .models import GoldenTask

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
_GOLDEN_PATH = _FIXTURES_DIR / "golden.json"


def load_golden(path: Path | None = None) -> list[GoldenTask]:
    """Load the golden task set from fixtures/golden.json (or an override path)."""
    p = path or _GOLDEN_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [
        GoldenTask(
            task_id=item["task_id"],
            prompt=item["prompt"],
            category=item["category"],
            expected=item["expected"],
            adversarial=item.get("adversarial", False),
            context=item.get("context", {}),
        )
        for item in raw
    ]


def golden_by_id(task_id: str, path: Path | None = None) -> GoldenTask | None:
    """Return one golden task by id, or None if not found."""
    for t in load_golden(path):
        if t.task_id == task_id:
            return t
    return None
