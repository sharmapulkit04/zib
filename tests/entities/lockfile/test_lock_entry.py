"""LockEntry conformance-FSM tests — the centerpiece of zib's correctness story.

These prove the load-bearing behavior we hardened: repin() advances the pin but never the
confirmed baseline, so the owed delta accumulates from the *last confirmed* point and
nothing is silently absorbed; confirm() (incl. `confirm --to` recovery) is the only way the
baseline moves.
"""

from __future__ import annotations

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
)


def _pin(tag: str) -> Pin:
    """Build a distinct Pin from a single char/digit (commit + matching content hash)."""
    return Pin(CommitSha(tag * 40), ContentHash("sha256:" + tag * 64))


A, B, C = _pin("1"), _pin("2"), _pin("3")


def _entry(pin: Pin = A, ref_type: RefKind = RefKind.SEMVER) -> LockEntry:
    return LockEntry(name=RefName("openspec"), ref_type=ref_type, resolved="2.1.0", pin=pin)


def test_fresh_entry_has_owed_delta_until_confirmed():
    entry = _entry()
    assert entry.confirmed_through is None
    assert entry.has_owed_delta() is True


def test_confirm_clears_owed_delta():
    entry = _entry()
    entry.confirm(entry.pin)
    assert entry.confirmed_through == A
    assert entry.has_owed_delta() is False


def test_repin_advances_pin_but_not_confirmed():
    entry = _entry()
    entry.confirm(A)
    entry.repin(resolved="2.2.0", ref_type=RefKind.SEMVER, pin=B)
    assert entry.pin == B
    assert entry.confirmed_through == A          # baseline untouched
    assert entry.has_owed_delta() is True        # B leads A


def test_repeated_repins_accumulate_from_last_confirmed():
    entry = _entry()
    entry.confirm(A)
    entry.repin(resolved="2.2.0", ref_type=RefKind.SEMVER, pin=B)
    entry.repin(resolved="2.3.0", ref_type=RefKind.SEMVER, pin=C)
    # Two bumps, no confirm in between: baseline is still A, so the owed delta spans A..C.
    assert entry.confirmed_through == A
    assert entry.pin == C
    assert entry.has_owed_delta() is True


def test_confirm_to_ancestor_recovers_over_assertion():
    entry = _entry()
    entry.repin(resolved="2.3.0", ref_type=RefKind.SEMVER, pin=C)
    entry.confirm(C)                # agent over-asserted "done through C"
    assert entry.has_owed_delta() is False
    entry.confirm(B)               # `confirm --to` walks the baseline back to B
    assert entry.confirmed_through == B
    assert entry.has_owed_delta() is True   # B trails the pin C again


def test_confirming_current_pin_after_repin_clears_delta():
    entry = _entry()
    entry.confirm(A)
    entry.repin(resolved="2.2.0", ref_type=RefKind.SEMVER, pin=B)
    entry.confirm(entry.pin)       # agent applied the delta and confirmed through B
    assert entry.has_owed_delta() is False


def test_rev_pin_is_frozen():
    assert _entry(ref_type=RefKind.REV).is_frozen() is True
    assert _entry(ref_type=RefKind.SEMVER).is_frozen() is False
