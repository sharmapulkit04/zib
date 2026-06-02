"""Scenario test for confirm_reference — real capability, fake stores, FakeGitPort.

No rules are mocked (the capability orchestrates the entity's confirm() move + the git
port's ancestry check directly). Outcomes are asserted through the fake lockfile store —
exactly what `outdated` / the session poll reads (``has_owed_delta``) — per CLAUDE.md's
"assert concrete outcomes via the fake stores."

Covers solution spec §9.3:
  - confirm (no arg)  → baseline = current pin; owed-delta closes
  - confirm --to <ancestor> → baseline moves BACK; owed-delta re-opens (recovery)
  - confirm --to <non-ancestor> → ValueError (over-assertion cannot land on a fork)
  - confirm --to without a content hash → ValueError (baseline must carry its integrity hash)
  - confirm an unknown reference → ValueError
"""

from __future__ import annotations

import pytest

from tests.capabilities.confirm_reference_scenarios import (
    PIN_COMMIT,
    PRIOR_COMMIT,
    PRIOR_CONTENT_HASH,
    SCENARIOS,
    SOURCE,
    UNRELATED_COMMIT,
)
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import FakeLockfileStore, FakeManifestStore
from zib.core.capabilities.confirm_reference.confirm_reference import (
    ConfirmReference,
    ConfirmResult,
)
from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
    RefSpec,
    Role,
)

PIN_CONTENT_HASH = "sha256:" + ("a" * 64)


def _wire():
    """Seed: a SEMVER ref 'spec' pinned at PIN_COMMIT, nothing confirmed yet.

    Registers PRIOR_COMMIT as an ancestor of PIN_COMMIT in the git port (the retained
    one-step-back target); UNRELATED_COMMIT is left non-ancestral (default False).
    """
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("spec-driven-development"),
            source=SOURCE,
            spec=RefSpec(RefKind.SEMVER, "^2.0.0"),
        )
    )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)

    entry = LockEntry(
        name=RefName("spec"),
        ref_type=RefKind.SEMVER,
        resolved="2.1.0",
        pin=Pin(CommitSha(PIN_COMMIT), ContentHash(PIN_CONTENT_HASH)),
    )
    lockfile = Lockfile()
    lockfile.put(entry)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)

    git = FakeGitPort()
    git.set_ancestry(SOURCE, PRIOR_COMMIT, PIN_COMMIT)

    cap = ConfirmReference(manifest_store, lockfile_store, git)
    return cap, lockfile_store


def _entry_after(lockfile_store):
    return lockfile_store.read().get(RefName("spec"))


@pytest.mark.parametrize("key", sorted(SCENARIOS.keys()))
def test_confirm_scenarios(key):
    scenario = SCENARIOS[key]
    cap, lockfile_store = _wire()

    # Precondition shared by every scenario: nothing confirmed yet -> owed delta is open.
    assert _entry_after(lockfile_store).has_owed_delta() is True

    inp = scenario["input"]
    to_commit = CommitSha(inp["to_commit"]) if inp["to_commit"] else None
    to_hash = ContentHash(inp["to_content_hash"]) if inp["to_content_hash"] else None

    result = cap.execute(
        name=inp["name"], to_commit=to_commit, to_content_hash=to_hash
    )

    expect = scenario["expect"]
    assert isinstance(result, ConfirmResult)
    assert result.name == "spec"
    assert result.confirmed_commit == expect["confirmed_commit"]

    entry = _entry_after(lockfile_store)
    assert entry.confirmed_through is not None
    assert str(entry.confirmed_through.commit) == expect["confirmed_commit"]
    assert entry.has_owed_delta() is expect["has_owed_delta"]
    assert entry.is_frozen() is expect["is_frozen"]


def test_confirm_no_arg_uses_current_pin_hash_as_baseline():
    # confirm <name> captures the WHOLE pin (commit + content_hash), not just the commit.
    cap, lockfile_store = _wire()
    cap.execute(name="spec")
    entry = _entry_after(lockfile_store)
    assert str(entry.confirmed_through.commit) == PIN_COMMIT
    assert str(entry.confirmed_through.content_hash) == PIN_CONTENT_HASH


def test_confirm_to_non_ancestor_raises():
    # Over-assertion recovery may only land on a genuine ancestor of the pin.
    cap, lockfile_store = _wire()
    with pytest.raises(ValueError):
        cap.execute(
            name="spec",
            to_commit=CommitSha(UNRELATED_COMMIT),
            to_content_hash=ContentHash("sha256:" + ("c" * 64)),
        )
    # Mutation rejected before persistence: baseline is still unset.
    assert _entry_after(lockfile_store).confirmed_through is None


def test_confirm_to_without_content_hash_raises():
    # The baseline carries a content_hash to integrity-check its retained tree (§9.3/§10).
    cap, lockfile_store = _wire()
    with pytest.raises(ValueError):
        cap.execute(name="spec", to_commit=CommitSha(PRIOR_COMMIT))
    assert _entry_after(lockfile_store).confirmed_through is None


def test_confirm_unknown_reference_raises():
    cap, _ = _wire()
    with pytest.raises(ValueError):
        cap.execute(name="missing")


def test_confirm_no_arg_is_idempotent_on_pin():
    # Re-confirming after catching up stays caught up (owed delta stays closed).
    cap, lockfile_store = _wire()
    cap.execute(name="spec")
    assert _entry_after(lockfile_store).has_owed_delta() is False
    cap.execute(name="spec")
    entry = _entry_after(lockfile_store)
    assert entry.has_owed_delta() is False
    assert str(entry.confirmed_through.commit) == PIN_COMMIT


def test_confirm_to_after_full_confirm_recovers_baseline():
    # Full sequence: catch up to pin, then realize over-assertion and move BACK to ancestor.
    cap, lockfile_store = _wire()
    cap.execute(name="spec")
    assert _entry_after(lockfile_store).has_owed_delta() is False

    result = cap.execute(
        name="spec",
        to_commit=CommitSha(PRIOR_COMMIT),
        to_content_hash=ContentHash(PRIOR_CONTENT_HASH),
    )
    assert result.confirmed_commit == PRIOR_COMMIT
    entry = _entry_after(lockfile_store)
    assert str(entry.confirmed_through.commit) == PRIOR_COMMIT
    assert entry.has_owed_delta() is True
