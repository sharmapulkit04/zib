"""Scenario tests for the list_references capability (Query).

Real aggregates wired to the fake persistence stores (no mocking of rules —
CLAUDE.md). Each scenario seeds the manifest + lockfile directly, runs the
capability, and asserts the EXACT ordered inventory rows and their concrete
field values. An owed delta is produced the real way: repin past the confirmed
baseline so ``LockEntry.has_owed_delta()`` reports it.
"""

from __future__ import annotations

import pytest

from tests.capabilities.list_references_scenarios import SCENARIOS
from tests.ports.persistence.fakes import FakeLockfileStore, FakeManifestStore
from zib.core.capabilities.list_references.list_references import (
    ListReferences,
    RefSummary,
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

# Deterministic, distinct shas/hashes so each pin is independently addressable.
_BASE_SHA = "a" * 40
_BASE_HASH = "sha256:" + "1" * 64
_AHEAD_SHA = "b" * 40
_AHEAD_HASH = "sha256:" + "2" * 64


def _spec(seed) -> RefSpec:
    kind = RefKind(seed["ref_type"])
    if kind is RefKind.LATEST:
        return RefSpec(RefKind.LATEST, None)
    return RefSpec(kind, seed["spec_value"])


def _build(seed_list):
    """Seed a manifest + lockfile from the scenario's reference descriptors."""
    manifest = Manifest()
    lockfile = Lockfile()
    for seed in seed_list:
        ref = RefName(seed["name"])
        manifest.add(
            ReferenceEntry(
                name=ref,
                role=Role(seed["role"]),
                source=f"acme/{seed['name']}",
                spec=_spec(seed),
            )
        )
        if not seed.get("pinned"):
            continue
        baseline = Pin(CommitSha(_BASE_SHA), ContentHash(_BASE_HASH))
        lock_type = RefKind(seed.get("lock_type", seed["ref_type"]))
        entry = LockEntry(
            name=ref,
            ref_type=lock_type,
            resolved=seed["resolved"],
            pin=baseline,
            confirmed_through=baseline,
        )
        if seed.get("owed"):
            # Advance the pin past the confirmed baseline the real way -> owed delta.
            entry.repin(
                resolved=seed["resolved"],
                ref_type=lock_type,
                pin=Pin(CommitSha(_AHEAD_SHA), ContentHash(_AHEAD_HASH)),
            )
        lockfile.put(entry)

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    return manifest_store, lockfile_store


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_list_references_scenarios(key):
    scenario = SCENARIOS[key]
    manifest_store, lockfile_store = _build(scenario["input"]["seed"])

    cap = ListReferences(manifest_store, lockfile_store)
    result = cap.execute()

    expect = scenario["expect"]
    assert len(result) == expect["count"]
    assert all(isinstance(row, RefSummary) for row in result)

    actual_rows = [
        (r.name, r.role, r.ref_type, r.resolved, r.owed_delta) for r in result
    ]
    assert actual_rows == expect["rows"]


def test_empty_manifest_returns_empty_list():
    """No declared references -> []. Both stores are read, neither is written."""
    manifest_store = FakeManifestStore()
    lockfile_store = FakeLockfileStore()

    cap = ListReferences(manifest_store, lockfile_store)
    result = cap.execute()

    assert result == []
    # Query capability: it never persists.
    assert manifest_store.exists() is False
    assert lockfile_store.exists() is False


def test_result_is_sorted_by_name_regardless_of_declaration_order():
    """Declared z, a, m -> rows come back a, m, z."""
    seed = [
        {"name": "z-ref", "role": "r", "ref_type": "tag", "spec_value": "v1", "pinned": False},
        {"name": "a-ref", "role": "r", "ref_type": "tag", "spec_value": "v1", "pinned": False},
        {"name": "m-ref", "role": "r", "ref_type": "tag", "spec_value": "v1", "pinned": False},
    ]
    manifest_store, lockfile_store = _build(seed)

    result = ListReferences(manifest_store, lockfile_store).execute()

    assert [r.name for r in result] == ["a-ref", "m-ref", "z-ref"]


def test_pinned_and_not_installed_coexist_with_correct_flags():
    """A pinned ref reports its lock state; a pending ref reports 'not installed'."""
    seed = [
        {
            "name": "live",
            "role": "spec",
            "ref_type": "semver",
            "spec_value": "^1.0.0",
            "pinned": True,
            "resolved": "1.0.0",
            "owed": False,
        },
        {
            "name": "pending",
            "role": "spec",
            "ref_type": "branch",
            "spec_value": "develop",
            "pinned": False,
        },
    ]
    manifest_store, lockfile_store = _build(seed)

    rows = ListReferences(manifest_store, lockfile_store).execute()

    by_name = {r.name: r for r in rows}
    assert by_name["live"].resolved == "1.0.0"
    assert by_name["live"].ref_type == "semver"
    assert by_name["live"].owed_delta is False
    assert by_name["pending"].resolved == "not installed"
    assert by_name["pending"].ref_type == "branch"
    assert by_name["pending"].owed_delta is False


def test_not_yet_installed_with_owed_left_false_even_if_unconfirmed_pin():
    """An installed-but-never-confirmed pin owes a delta (confirmed_through is None)."""
    seed = [
        {
            "name": "fresh",
            "role": "spec",
            "ref_type": "semver",
            "spec_value": "^1.0.0",
            "pinned": True,
            "resolved": "1.0.0",
        },
    ]
    # pinned but no owed flag -> confirmed_through == pin in _build; flip it here:
    manifest_store, lockfile_store = _build(seed)
    lockfile = lockfile_store.read()
    entry = lockfile.get(RefName("fresh"))
    entry.confirmed_through = None  # never confirmed -> owes a delta
    lockfile_store.write(lockfile)

    rows = ListReferences(manifest_store, lockfile_store).execute()

    assert len(rows) == 1
    assert rows[0].owed_delta is True
