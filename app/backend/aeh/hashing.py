"""SHA-256 content hashing over canonical bytes."""

from __future__ import annotations

import hashlib
from typing import Any

from .canonical import canonical_bytes


def sha256_hex(data: bytes) -> str:
    """Return the SHA-256 hex digest of the given bytes."""
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """Deterministic sha256 over the canonical serialization of obj (prefixed)."""
    return "sha256:" + sha256_hex(canonical_bytes(obj))
