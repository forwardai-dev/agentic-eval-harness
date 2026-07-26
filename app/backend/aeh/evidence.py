"""Seals a run into a hash-chained, Ed25519-signed evidence record.

Reuses the AAH pattern: canonical bytes -> sha256 content hash -> Ed25519
signature, chained via prev_hash/this_hash so any later mutation of any past
record breaks the chain. `verify_record` re-checks it three independent ways
(integrity hash, signature, decision-replay) — tampering breaks all three.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from . import gate as gate_mod
from .canonical import canonical_bytes
from .hashing import sha256_hex
from .signer import DEMO_SEED, Ed25519Signer, Ed25519Verifier

GENESIS = "sha256:GENESIS"


@dataclass
class EvidenceRecord:
    """One hash-chained, signed ledger entry sealing a run's Trace payload."""

    run_id: str
    payload: dict  # the canonical Trace.to_dict()
    prev_hash: str
    timestamp: str
    public_key_hex: str
    signature: str = ""
    this_hash: str = ""

    def _presign_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "payload": self.payload,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "public_key_hex": self.public_key_hex,
        }

    def presign_bytes(self) -> bytes:
        """Canonical bytes that are hashed and signed."""
        return canonical_bytes(self._presign_dict())

    def to_dict(self) -> dict:
        return {
            **self._presign_dict(),
            "signature": self.signature,
            "this_hash": self.this_hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceRecord":
        return cls(
            run_id=d["run_id"],
            payload=d["payload"],
            prev_hash=d["prev_hash"],
            timestamp=d["timestamp"],
            public_key_hex=d["public_key_hex"],
            signature=d.get("signature", ""),
            this_hash=d.get("this_hash", ""),
        )


def seal(
    run_id: str, payload: dict, signer: Ed25519Signer, prev_hash: str, timestamp: str
) -> EvidenceRecord:
    """Seal a run's payload into a signed, hash-chained evidence record."""
    rec = EvidenceRecord(
        run_id=run_id,
        payload=payload,
        prev_hash=prev_hash,
        timestamp=timestamp,
        public_key_hex=signer.public_key_hex,
    )
    b = rec.presign_bytes()
    rec.signature = signer.sign(b)
    rec.this_hash = "sha256:" + sha256_hex(b)
    return rec


class Ledger:
    """Append-only, hash-chained ledger of evidence records, keyed by run_id.

    Uses a fixed demo Ed25519 key (seeded) so the whole chain is reproducible
    offline without persisting a private key file.
    """

    def __init__(self, signer: Ed25519Signer | None = None) -> None:
        self.signer = signer or Ed25519Signer.generate(seed=DEMO_SEED)
        self._records: dict[str, EvidenceRecord] = {}
        self._order: list[str] = []

    def head(self) -> str:
        """The hash of the most recently appended record, or GENESIS if empty."""
        return self._records[self._order[-1]].this_hash if self._order else GENESIS

    def append(
        self, run_id: str, payload: dict, timestamp: str = "1970-01-01T00:00:00Z"
    ) -> EvidenceRecord:
        """Seal and append a new record, chained to the current head."""
        rec = seal(run_id, payload, self.signer, self.head(), timestamp)
        self._records[run_id] = rec
        self._order.append(run_id)
        return rec

    def get(self, run_id: str) -> EvidenceRecord | None:
        """Fetch a sealed record by run_id."""
        return self._records.get(run_id)

    def list_records(self) -> list[EvidenceRecord]:
        """All sealed records in append order."""
        return [self._records[rid] for rid in self._order]

    def prev_hash_for(self, run_id: str) -> str | None:
        """The prev_hash a record for run_id *should* chain to, or None if unknown."""
        if run_id not in self._order:
            return None
        idx = self._order.index(run_id)
        return self._records[self._order[idx - 1]].this_hash if idx > 0 else GENESIS

    def verify_chain(self) -> bool:
        """Re-walk the whole chain; True iff every link's hash + signature hold."""
        prev = GENESIS
        verifier = Ed25519Verifier()
        for rec in self.list_records():
            if rec.prev_hash != prev:
                return False
            b = rec.presign_bytes()
            if rec.this_hash != "sha256:" + sha256_hex(b):
                return False
            if not verifier.verify(b, rec.signature, rec.public_key_hex):
                return False
            prev = rec.this_hash
        return True


def _replay_decision(payload: dict) -> bool:
    """Recompute the single-run gate from the sealed payload's own metrics and
    findings, and compare it to the gate the payload claims. This is the
    "decision-replay" check — it catches tampering that flips a finding's
    severity or the gate string without the metrics that should back it up."""
    metrics = payload.get("metrics", {})
    accuracy = metrics.get("accuracy", 0.0)
    blocking = sum(
        1 for f in payload.get("findings", []) if f.get("severity") == "blocking"
    )
    status, _ = gate_mod.decide_run(accuracy, blocking)
    return status == payload.get("gate")


def verify_record(
    record: EvidenceRecord, expected_prev_hash: str | None = None
) -> dict:
    """Verify one record three independent ways: content-hash integrity,
    Ed25519 signature, and gate decision-replay. Optionally also checks it
    links to `expected_prev_hash` in the chain."""
    b = record.presign_bytes()
    integrity = record.this_hash == "sha256:" + sha256_hex(b)
    signature_ok = Ed25519Verifier().verify(b, record.signature, record.public_key_hex)
    decision_ok = _replay_decision(record.payload)
    chain_ok = (
        True if expected_prev_hash is None else (record.prev_hash == expected_prev_hash)
    )
    return {
        "integrity": integrity,
        "signature": signature_ok,
        "decision": decision_ok,
        "chain": chain_ok,
        "verified": integrity and signature_ok and decision_ok and chain_ok,
    }


def tamper(record: EvidenceRecord) -> EvidenceRecord:
    """Return a mutated COPY of the record: flips the first finding's severity
    (or the gate, if there are no findings). `this_hash`/`signature` are left
    stale on purpose — that staleness is exactly what `verify_record` catches."""
    mutated = copy.deepcopy(record)
    findings = mutated.payload.get("findings", [])
    if findings:
        findings[0]["severity"] = (
            "info" if findings[0]["severity"] == "blocking" else "blocking"
        )
    else:
        mutated.payload["gate"] = (
            "PASS" if mutated.payload.get("gate") == "FAIL" else "FAIL"
        )
    return mutated
