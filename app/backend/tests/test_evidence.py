"""Signed, hash-chained evidence: sign->verify round-trip and tamper rejection.

The tamper test is the "caught three ways" regression pattern reused from
AAH: mutating a sealed record must break integrity, signature, AND the
decision-replay check, independently of each other.
"""

from __future__ import annotations

from aeh import evidence
from aeh.golden import golden_by_id
from aeh.workflow import Orchestrator


def _sealed_record(task_id: str):
    task = golden_by_id(task_id)
    trace = Orchestrator().run(task)
    ledger = evidence.Ledger()
    rec = ledger.append(trace.run_id, trace.to_dict())
    return ledger, rec, trace


def test_sign_then_verify_round_trips_on_a_clean_run():
    _, rec, _ = _sealed_record("gt-001")
    result = evidence.verify_record(rec)
    assert result["integrity"] is True
    assert result["signature"] is True
    assert result["decision"] is True
    assert result["verified"] is True


def test_sign_then_verify_round_trips_on_a_caught_adversarial_run():
    _, rec, trace = _sealed_record("gt-004")
    assert trace.gate == "FAIL"
    result = evidence.verify_record(rec)
    assert result["verified"] is True


def test_two_fresh_seals_of_the_same_task_are_byte_identical():
    _, rec1, _ = _sealed_record("gt-001")
    _, rec2, _ = _sealed_record("gt-001")
    assert rec1.this_hash == rec2.this_hash
    assert rec1.signature == rec2.signature


def test_tamper_breaks_integrity_signature_and_decision_replay():
    _, rec, _ = _sealed_record("gt-004")  # has a blocking finding to flip
    mutated = evidence.tamper(rec)
    result = evidence.verify_record(mutated)
    assert result["integrity"] is False, (
        "content hash must no longer match stale this_hash"
    )
    assert result["signature"] is False, (
        "signature was computed over the pre-tamper bytes"
    )
    assert result["decision"] is False, (
        "recomputed gate must no longer match the claimed gate"
    )
    assert result["verified"] is False


def test_tamper_on_a_clean_run_also_breaks_all_three_checks():
    _, rec, _ = _sealed_record(
        "gt-001"
    )  # no findings -> tamper() flips the gate field instead
    mutated = evidence.tamper(rec)
    result = evidence.verify_record(mutated)
    assert result["integrity"] is False
    assert result["signature"] is False
    assert result["verified"] is False


def test_ledger_chain_verifies_across_multiple_appends():
    ledger = evidence.Ledger()
    for task_id in ("gt-001", "gt-002", "gt-003"):
        trace = Orchestrator().run(golden_by_id(task_id))
        ledger.append(trace.run_id, trace.to_dict())
    assert ledger.verify_chain() is True


def test_ledger_chain_breaks_if_a_past_record_is_mutated_in_place():
    ledger = evidence.Ledger()
    for task_id in ("gt-001", "gt-002", "gt-003"):
        trace = Orchestrator().run(golden_by_id(task_id))
        ledger.append(trace.run_id, trace.to_dict())
    ledger._records[ledger._order[0]].payload["gate"] = "TAMPERED"
    assert ledger.verify_chain() is False
