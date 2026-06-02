"""Scenario tests for the show_reference capability (Query).

Real aggregates wired to the fake persistence stores (no mocking of rules — the only
logic is the pure ``_spec_repr`` projection, exercised through the capability). Each
scenario seeds the manifest and (optionally) the lockfile, runs the capability, and
asserts every RefDetail field to a concrete value. Missing / invalid names raise.
"""

from __future__ import annotations

import pytest

from tests.capabilities.show_reference_scenarios import SCENARIOS
from tests.ports.persistence.fakes import FakeLockfileStore, FakeManifestStore
from zib.core.capabilities.show_reference.show_reference import (
    RefDetail,
    ShowReference,
)
from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefName,
    RefSpec,
    Role,
)

_HASH = "sha256:" + "1" * 64


def _build(seed):
    """Seed a manifest (+ optional lockfile) for one reference from a scenario seed."""
    ref = RefName(seed["name"])
    spec = RefSpec.from_manifest(
        version=seed.get("version"),
        branch=seed.get("branch"),
        tag=seed.get("tag"),
        rev=seed.get("rev"),
    )
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=ref,
            role=Role(seed["role"]),
            source=seed["source"],
            spec=spec,
            subdirectory=seed.get("subdirectory"),
            description=seed.get("description"),
        )
    )

    lockfile = Lockfile()
    lock = seed.get("lock")
    if lock is not None:
        pin = Pin(CommitSha(lock["commit"]), ContentHash(_HASH))
        confirmed = (
            None
            if lock["confirmed"] is None
            else Pin(CommitSha(lock["confirmed"]), ContentHash(_HASH))
        )
        lockfile.put(
            LockEntry(
                name=ref,
                ref_type=spec.kind,
                resolved=lock["resolved"],
                pin=pin,
                confirmed_through=confirmed,
            )
        )

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    return manifest_store, lockfile_store


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_show_reference_scenarios(key):
    scenario = SCENARIOS[key]
    seed = scenario["input"]["seed"]
    expect = scenario["expect"]

    manifest_store, lockfile_store = _build(seed)
    cap = ShowReference(manifest_store, lockfile_store)

    detail = cap.execute(scenario["input"]["show"])

    assert isinstance(detail, RefDetail)
    assert detail.name == expect["name"]
    assert detail.role == expect["role"]
    assert detail.source == expect["source"]
    assert detail.spec_repr == expect["spec_repr"]
    assert detail.resolved == expect["resolved"]
    assert detail.pinned_commit == expect["pinned_commit"]
    assert detail.confirmed_commit == expect["confirmed_commit"]
    assert detail.subdirectory == expect["subdirectory"]
    assert detail.description == expect["description"]


def test_show_missing_reference_raises_clear_error():
    seed = SCENARIOS["installed_semver_caught_up"]["input"]["seed"]
    manifest_store, lockfile_store = _build(seed)
    cap = ShowReference(manifest_store, lockfile_store)

    with pytest.raises(ValueError, match="not declared"):
        cap.execute("ghost")


def test_show_invalid_name_raises_at_boundary():
    seed = SCENARIOS["installed_semver_caught_up"]["input"]["seed"]
    manifest_store, lockfile_store = _build(seed)
    cap = ShowReference(manifest_store, lockfile_store)

    with pytest.raises(ValueError):
        cap.execute("Bad Name")


def test_show_is_a_pure_query_no_writes():
    """A query reads only: it never re-writes the manifest or lockfile."""

    class _CountingManifestStore(FakeManifestStore):
        writes = 0

        def write(self, manifest):  # type: ignore[override]
            type(self).writes += 1
            super().write(manifest)

    class _CountingLockfileStore(FakeLockfileStore):
        writes = 0

        def write(self, lockfile):  # type: ignore[override]
            type(self).writes += 1
            super().write(lockfile)

    seed = SCENARIOS["installed_owed_delta"]["input"]["seed"]
    base_m, base_l = _build(seed)

    manifest_store = _CountingManifestStore()
    manifest_store.write(base_m.read())
    lockfile_store = _CountingLockfileStore()
    lockfile_store.write(base_l.read())
    # reset counters after seeding
    _CountingManifestStore.writes = 0
    _CountingLockfileStore.writes = 0

    cap = ShowReference(manifest_store, lockfile_store)
    cap.execute("spec")

    assert _CountingManifestStore.writes == 0
    assert _CountingLockfileStore.writes == 0
