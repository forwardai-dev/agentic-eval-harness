"""Deterministic canonical JSON bytes — the basis for content-addressing.

Sorted keys, tight separators, UTF-8, no NaN. The same logical object always
serializes to the same bytes, which is what makes hashing/signing reproducible
and what makes "run it twice, get the same evidence hash" true.
"""

from __future__ import annotations

import json
from typing import Any


def canonical_bytes(obj: Any) -> bytes:
    """Serialize obj to canonical, deterministic UTF-8 bytes."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_str(obj: Any) -> str:
    """Serialize an object to canonical, deterministic JSON text."""
    return canonical_bytes(obj).decode("utf-8")
