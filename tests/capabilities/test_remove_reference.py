"""Scenario tests for the remove_reference capability.

Real rule (render_inventory) + real aggregates wired to the fake persistence stores
(no mocking of rules — CLAUDE.md). Seeds the manifest/lockfile/content directly, runs
the capability, and asserts concrete surviving state across every store and the block.
"""

from __future__ import annotations

import pytest

from tests.capabilities.remove_reference_scenarios import SCENARIOS
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.remove_reference.remove_reference import (
    RemoveReference,
    RemoveResult,
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
    TreeEntry,
)

# Distinct, deterministic 40-hex shas / hashes per reference name.
_COMMITS = {
    "spec": "a" * 40,
    "style": "b" * 40,
}
_HASHES = {
    "spec": "sha256:" + "1" * 64,
    "style": "sha256:" + "2" * 64,
}


def _build(names):
    """Seed a manifest + lockfile + content for ``names`` (each pinned & materialized)."""
    manifest = Manifest()
    lockfile = Lockfile()
    content = FakeContentStore()
    for name in names:
        ref = RefName(name)
        manifest.add(
            ReferenceEntry(
                name=ref,
                role=Role(f"role-{name}"),
                source=f"acme/{name}",
                spec=RefSpec(RefKind.SEMVER, "^1.0.0"),
                description=f"the {name} reference",
            )
        )
        pin = Pin(CommitSha(_COMMITS[name]), ContentHash(_HASHES[name]))
        lockfile.put(
            LockEntry(
                name=ref,
                ref_type=RefKind.SEMVER,
                resolved="1.0.0",
                pin=pin,
                confirmed_through=pin,
            )
        )
        content.materialize(ref, "1.0.0", [TreeEntry(f"{name}.md", 0o100644, b"x")])

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    return manifest_store, lockfile_store, content


def _capability(names):
    manifest_store, lockfile_store, content = _build(names)
    agent = FakeAgentFileStore()
    cap = RemoveReference(manifest_store, lockfile_store, content, agent)
    return cap, manifest_store, lockfile_store, content, agent


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_remove_reference_scenarios(key):
    scenario = SCENARIOS[key]
    spec = scenario["input"]
    expect = scenario["expect"]

    cap, manifest_store, lockfile_store, content, agent = _capability(spec["seed"])

    result = cap.execute(spec["remove"])

    # result
    assert isinstance(result, RemoveResult)
    assert result.name == expect["result_name"]

    manifest = manifest_store.read()
    lockfile = lockfile_store.read()

    # manifest
    for name in expect["manifest_has"]:
        assert manifest.by_name(RefName(name)) is not None
    for name in expect["manifest_missing"]:
        assert manifest.by_name(RefName(name)) is None

    # lockfile
    assert len(lockfile) == expect["lock_len"]
    for name in expect["lock_has"]:
        assert lockfile.get(RefName(name)) is not None
    for name in expect["lock_missing"]:
        assert lockfile.get(RefName(name)) is None

    # content
    for name, present in expect["content_present"].items():
        ref = RefName(name)
        if present:
            assert content.read_tree(ref, "1.0.0") == [
                TreeEntry(f"{name}.md", 0o100644, b"x")
            ]
        else:
            with pytest.raises(KeyError):
                content.read_tree(ref, "1.0.0")

    # rebuilt inventory block
    assert agent.last_block is not None
    for name in expect["block_mentions"]:
        assert name in agent.last_block
    for name in expect["block_omits"]:
        assert name not in agent.last_block
    if not expect["block_mentions"]:
        assert "No references are pinned yet" in agent.last_block


def test_remove_missing_reference_raises_clear_error():
    cap, manifest_store, lockfile_store, content, agent = _capability(["spec"])

    with pytest.raises(ValueError, match="not declared"):
        cap.execute("ghost")

    # nothing changed: the existing reference and its content survive untouched.
    assert manifest_store.read().by_name(RefName("spec")) is not None
    assert lockfile_store.read().get(RefName("spec")) is not None
    assert content.read_tree(RefName("spec"), "1.0.0") == [
        TreeEntry("spec.md", 0o100644, b"x")
    ]
    # the agent block was never rewritten on the failed remove.
    assert agent.last_block is None


def test_remove_surviving_owed_delta_surfaces_in_block():
    """A survivor with an owed delta still shows its UPDATE PENDING line after removal."""
    manifest_store, lockfile_store, content = _build(["spec", "style"])
    # advance the pin of the survivor past its confirmed baseline -> owed delta.
    lockfile = lockfile_store.read()
    survivor = lockfile.get(RefName("style"))
    new_pin = Pin(CommitSha("c" * 40), ContentHash("sha256:" + "3" * 64))
    survivor.repin(resolved="1.1.0", ref_type=RefKind.SEMVER, pin=new_pin)
    lockfile_store.write(lockfile)

    agent = FakeAgentFileStore()
    cap = RemoveReference(manifest_store, lockfile_store, content, agent)
    cap.execute("spec")

    assert survivor.has_owed_delta() is True
    assert "UPDATE PENDING" in agent.last_block
    assert "zib diff style" in agent.last_block
    assert "spec" not in agent.last_block


def test_remove_invalid_name_raises_at_boundary():
    cap, *_ = _capability(["spec"])
    with pytest.raises(ValueError):
        cap.execute("Bad Name")
