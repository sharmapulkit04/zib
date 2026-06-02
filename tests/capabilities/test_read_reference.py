"""Scenario tests for the read_reference capability (``zib cat <name>``).

Real aggregates wired to the fake persistence stores (no mocking of rules — CLAUDE.md):
the manifest declares the references, the lockfile pins them, the content store holds the
materialized trees. The capability is a pure read, so we assert (a) the exact tree the
agent reads back and (b) that nothing in any store changed; and we cover every
unavailable-read path as a distinct, actionable ValueError.
"""

from __future__ import annotations

import pytest

from tests.capabilities.read_reference_scenarios import SCENARIOS, SEED
from tests.ports.persistence.fakes import (
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.read_reference.read_reference import ReadReference
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
    TreeEntry,
)

# Distinct, deterministic 40-hex commits / content hashes per reference name.
_COMMITS = {"spec": "a" * 40, "style": "b" * 40, "guide": "c" * 40}
_HASHES = {
    "spec": "sha256:" + "1" * 64,
    "style": "sha256:" + "2" * 64,
    "guide": "sha256:" + "3" * 64,
}


def _spec_for(name: str) -> RefSpec:
    value = SEED[name]["spec_value"]
    if name == "guide":
        return RefSpec.from_manifest(branch=value)
    return RefSpec.from_manifest(version=value)


def _ref_type_for(name: str) -> RefKind:
    return RefKind.BRANCH if name == "guide" else RefKind.SEMVER


def _build(names):
    """Seed manifest + lockfile + materialized content for each name in ``names``."""
    manifest = Manifest()
    lockfile = Lockfile()
    content = FakeContentStore()
    for name in names:
        seed = SEED[name]
        ref = RefName(name)
        manifest.add(
            ReferenceEntry(
                name=ref,
                role=Role(seed["role"]),
                source=f"acme/{name}",
                spec=_spec_for(name),
            )
        )
        pin = Pin(CommitSha(_COMMITS[name]), ContentHash(_HASHES[name]))
        lockfile.put(
            LockEntry(
                name=ref,
                ref_type=_ref_type_for(name),
                resolved=seed["resolved"],
                pin=pin,
                confirmed_through=pin,
            )
        )
        tree = [
            TreeEntry(path, 0o100644, text.encode("utf-8"))
            for path, text in seed["tree"]
        ]
        content.materialize(ref, seed["resolved"], tree)

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    return manifest_store, lockfile_store, content


def _capability(names):
    manifest_store, lockfile_store, content = _build(names)
    cap = ReadReference(manifest_store, lockfile_store, content)
    return cap, manifest_store, lockfile_store, content


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_read_reference_scenarios(key):
    scenario = SCENARIOS[key]
    spec = scenario["input"]
    expect = scenario["expect"]

    cap, *_ = _capability(spec["seed"])

    tree = cap.execute(spec["read"])

    assert isinstance(tree, list)
    assert all(isinstance(entry, TreeEntry) for entry in tree)
    assert len(tree) == expect["file_count"]
    assert [entry.path for entry in tree] == expect["paths"]
    blobs = {entry.path: entry.blob for entry in tree}
    assert blobs == expect["blobs"]
    # every materialized file is a regular file (mode preserved on read-through).
    assert all(entry.mode == 0o100644 for entry in tree)


def test_read_is_pure_no_store_is_written():
    cap, manifest_store, lockfile_store, content = _capability(["spec"])

    before_manifest = manifest_store.read()
    before_lock = lockfile_store.read()

    cap.execute("spec")
    cap.execute("spec")  # idempotent: re-reading yields the same bytes, no mutation.

    # same aggregate objects, same pinned state — a query mutates nothing.
    assert manifest_store.read() is before_manifest
    assert lockfile_store.read() is before_lock
    assert len(lockfile_store.read()) == 1
    assert lockfile_store.read().get(RefName("spec")).resolved == "2.1.4"
    # the read returns a copy each time, identical in content.
    first = cap.execute("spec")
    second = cap.execute("spec")
    assert first == second
    assert first is not second


def test_read_undeclared_reference_raises():
    cap, *_ = _capability(["spec"])
    with pytest.raises(ValueError, match="not declared"):
        cap.execute("ghost")


def test_read_declared_but_unpinned_reference_raises():
    # Declare a reference in the manifest but leave it out of the lockfile.
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("json-mapping"),
            source="acme/spec",
            spec=RefSpec.from_manifest(version="^2.1.0"),
        )
    )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(Lockfile())
    cap = ReadReference(manifest_store, lockfile_store, FakeContentStore())

    with pytest.raises(ValueError, match="not pinned"):
        cap.execute("spec")


def test_read_pinned_but_unmaterialized_reference_raises():
    # Pin the reference but never materialize its content (e.g. fresh clone gap).
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("json-mapping"),
            source="acme/spec",
            spec=RefSpec.from_manifest(version="^2.1.0"),
        )
    )
    lockfile = Lockfile()
    pin = Pin(CommitSha("a" * 40), ContentHash("sha256:" + "1" * 64))
    lockfile.put(
        LockEntry(
            name=RefName("spec"),
            ref_type=RefKind.SEMVER,
            resolved="2.1.4",
            pin=pin,
            confirmed_through=pin,
        )
    )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    cap = ReadReference(manifest_store, lockfile_store, FakeContentStore())

    with pytest.raises(ValueError, match="not materialized"):
        cap.execute("spec")


def test_read_invalid_name_raises_at_boundary():
    cap, *_ = _capability(["spec"])
    with pytest.raises(ValueError):
        cap.execute("Bad Name")
