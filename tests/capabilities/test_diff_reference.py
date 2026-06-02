"""Scenario test for diff_reference — real capability + real NotesProcess, fake stores.

No rules are mocked: the capability orchestrates the lock entry's own conformance state
and the real ``NotesProcess`` (wired to ``FakeGitPort``), which runs the real
``parse_diff_counts`` + ``classify_magnitude`` rules. Outcomes are asserted as concrete
values — exactly what `zib diff` reports to the agent (spec §9.2).

Covers the three conformance positions:
  - pending owed delta  → has_pending True, delta surfaced, INCREMENTAL ⇒ read_whole False
  - caught up           → has_pending False, no delta
  - never confirmed     → first encounter ⇒ read_whole True, no delta

Plus: a major REWRITE flips read_whole on (§9.2 escape hatch), and diff mutates nothing.
"""

from __future__ import annotations

import pytest

from tests.capabilities.diff_reference_scenarios import (
    BASELINE_LINES,
    COMMIT_SUBJECT,
    INCREMENTAL_DIFF,
    PIN_COMMIT,
    PIN_CONTENT_HASH,
    PRIOR_COMMIT,
    PRIOR_CONTENT_HASH,
    SCENARIOS,
    SOURCE,
    SUBDIRECTORY,
)
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import FakeLockfileStore, FakeManifestStore
from zib.core.capabilities.diff_reference.diff_reference import (
    DiffReference,
    DiffResult,
)
from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.port.git_port import GitCommit
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
    RefSpec,
    Role,
    TreeEntry,
)


def _baseline_tree() -> list[TreeEntry]:
    """The from-side (PRIOR_COMMIT) tree — BASELINE_LINES newline-terminated lines."""
    blob = ("\n".join(f"line {i}" for i in range(BASELINE_LINES)) + "\n").encode()
    # BASELINE_LINES lines each ending in '\n' => BASELINE_LINES newlines.
    return [TreeEntry("spec.md", 0o100644, blob)]


def _git_with_incremental_delta() -> FakeGitPort:
    """A FakeGitPort that surfaces a small INCREMENTAL delta (PRIOR_COMMIT, PIN_COMMIT]."""
    git = FakeGitPort()
    git.add_rev(SOURCE, PRIOR_COMMIT)
    git.add_rev(SOURCE, PIN_COMMIT)
    git.set_tree(SOURCE, PRIOR_COMMIT, _baseline_tree())
    git.set_diff(SOURCE, PRIOR_COMMIT, PIN_COMMIT, INCREMENTAL_DIFF)
    git.set_log(
        SOURCE,
        PRIOR_COMMIT,
        PIN_COMMIT,
        [GitCommit(CommitSha(PIN_COMMIT), COMMIT_SUBJECT, "")],
    )
    return git


def _manifest_store() -> FakeManifestStore:
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("spec-driven-development"),
            source=SOURCE,
            spec=RefSpec(RefKind.SEMVER, "^2.0.0"),
            subdirectory=SUBDIRECTORY,
        )
    )
    store = FakeManifestStore()
    store.write(manifest)
    return store


def _lock_store(confirmed_through: Pin | None) -> FakeLockfileStore:
    """Seed a lockfile with 'spec' pinned at PIN_COMMIT and the given baseline."""
    entry = LockEntry(
        name=RefName("spec"),
        ref_type=RefKind.SEMVER,
        resolved="2.1.0",
        pin=Pin(CommitSha(PIN_COMMIT), ContentHash(PIN_CONTENT_HASH)),
        confirmed_through=confirmed_through,
    )
    lockfile = Lockfile()
    lockfile.put(entry)
    store = FakeLockfileStore()
    store.write(lockfile)
    return store


_PRIOR_PIN = Pin(CommitSha(PRIOR_COMMIT), ContentHash(PRIOR_CONTENT_HASH))
_PIN = Pin(CommitSha(PIN_COMMIT), ContentHash(PIN_CONTENT_HASH))

# Each scenario maps to the baseline (confirmed_through) that produces its conformance state.
_BASELINE_FOR_SCENARIO = {
    "pending_incremental_delta_is_surfaced": _PRIOR_PIN,  # baseline behind the pin
    "no_owed_delta_when_caught_up": _PIN,                  # baseline == pin
    "never_confirmed_reads_whole": None,                  # no baseline
}


@pytest.mark.parametrize("key", sorted(SCENARIOS.keys()))
def test_diff_scenarios(key):
    scenario = SCENARIOS[key]
    cap = DiffReference(
        _manifest_store(),
        _lock_store(_BASELINE_FOR_SCENARIO[key]),
        NotesProcess(_git_with_incremental_delta()),
    )

    result = cap.execute(name=scenario["input"]["name"])

    expect = scenario["expect"]
    assert isinstance(result, DiffResult)
    assert result.name == "spec"
    assert result.has_pending is expect["has_pending"]
    assert result.read_whole is expect["read_whole"]
    assert (result.delta is not None) is expect["has_delta"]


def test_pending_delta_carries_diff_log_and_incremental_magnitude():
    # The surfaced delta carries the real diff text, the commit log, and INCREMENTAL churn
    # (2 changed lines / 20 baseline lines = 0.1 < 0.5).
    from zib.core.rules.computation.delta.delta import Magnitude

    cap = DiffReference(
        _manifest_store(),
        _lock_store(_PRIOR_PIN),
        NotesProcess(_git_with_incremental_delta()),
    )
    result = cap.execute(name="spec")

    assert result.delta is not None
    assert result.delta.diff_text == INCREMENTAL_DIFF
    assert result.delta.magnitude is Magnitude.INCREMENTAL
    assert len(result.delta.commits) == 1
    assert result.delta.commits[0].subject == COMMIT_SUBJECT
    assert result.read_whole is False


def test_major_rewrite_flips_read_whole_on():
    # A diff that churns >= 50% of the baseline is a REWRITE: the agent re-reads the whole
    # reference (§9.2 escape hatch) even though a delta still exists.
    git = FakeGitPort()
    git.add_rev(SOURCE, PRIOR_COMMIT)
    git.add_rev(SOURCE, PIN_COMMIT)
    git.set_tree(SOURCE, PRIOR_COMMIT, _baseline_tree())  # 20 baseline lines
    # 15 insertions + 15 deletions = 30 changed / 20 = 1.5 churn >= 0.5 → REWRITE.
    rewrite_diff = "diff --git a/spec.md b/spec.md\n--- a/spec.md\n+++ b/spec.md\n"
    rewrite_diff += "".join(f"-old line {i}\n+new line {i}\n" for i in range(15))
    git.set_diff(SOURCE, PRIOR_COMMIT, PIN_COMMIT, rewrite_diff)

    cap = DiffReference(_manifest_store(), _lock_store(_PRIOR_PIN), NotesProcess(git))
    result = cap.execute(name="spec")

    assert result.has_pending is True
    assert result.read_whole is True
    assert result.delta is not None


def test_diff_mutates_nothing():
    # Read-only: the lock entry's baseline is unchanged after diff (spec §9.2).
    lock_store = _lock_store(_PRIOR_PIN)
    cap = DiffReference(_manifest_store(), lock_store, NotesProcess(_git_with_incremental_delta()))
    cap.execute(name="spec")

    entry = lock_store.read().get(RefName("spec"))
    assert str(entry.confirmed_through.commit) == PRIOR_COMMIT
    assert entry.has_owed_delta() is True


def test_undeclared_but_locked_reference_raises():
    # Locked but not declared in the manifest — diff has no source/subdir to compute against.
    cap = DiffReference(
        FakeManifestStore(),  # empty manifest
        _lock_store(_PRIOR_PIN),
        NotesProcess(_git_with_incremental_delta()),
    )
    with pytest.raises(ValueError):
        cap.execute(name="spec")


def test_declared_but_not_locked_reference_raises():
    cap = DiffReference(
        _manifest_store(),
        FakeLockfileStore(),  # empty lockfile
        NotesProcess(_git_with_incremental_delta()),
    )
    with pytest.raises(ValueError):
        cap.execute(name="spec")
