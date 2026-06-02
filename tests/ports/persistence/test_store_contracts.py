"""Contract tests for the persistence ports.

These assert the behavior ANY implementation (fake or real adapter) must satisfy. The
fakes must pass these before higher-level tests are allowed to trust them
(CLAUDE.md invariant 6). The same contract functions are intended to be re-run against
the real infrastructure adapters.
"""

from __future__ import annotations

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import CURRENT_LOCKFILE_VERSION, Lockfile
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
from zib.core.ports.persistence.stores import (
    AgentFileStore,
    ContentStore,
    LockfileStore,
    ManifestStore,
)
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)

_COMMIT_HEX = "a" * 40
_OTHER_HEX = "b" * 40


def _sample_manifest() -> Manifest:
    spec = RefSpec.from_manifest(version="^2.1.0")
    entry = ReferenceEntry(
        name=RefName("json-spec"),
        role=Role("json-mapping"),
        source="acme/json-spec",
        spec=spec,
        subdirectory="docs",
        description="JSON mapping conventions",
    )
    return Manifest(references=[entry])


def _sample_lockfile() -> Lockfile:
    pin = Pin(
        commit=CommitSha(_COMMIT_HEX),
        content_hash=ContentHash("sha256:" + "c" * 64),
    )
    entry = LockEntry(
        name=RefName("json-spec"),
        ref_type=RefKind.SEMVER,
        resolved="2.1.4",
        pin=pin,
    )
    lock = Lockfile()
    lock.put(entry)
    return lock


def _sample_tree() -> list[TreeEntry]:
    return [
        TreeEntry(path="a.md", mode=0o100644, blob=b"hello\n"),
        TreeEntry(path="b/c.md", mode=0o100644, blob=b"world\n"),
    ]


# --------------------------------------------------------------------------- ManifestStore


def test_manifest_store_satisfies_protocol() -> None:
    assert isinstance(FakeManifestStore(), ManifestStore)


def test_manifest_store_starts_absent_and_reads_empty() -> None:
    store = FakeManifestStore()
    assert store.exists() is False
    fresh = store.read()
    assert isinstance(fresh, Manifest)
    assert fresh.references == []
    assert fresh.poll is None


def test_manifest_store_exists_flips_after_write() -> None:
    store = FakeManifestStore()
    assert store.exists() is False
    store.write(_sample_manifest())
    assert store.exists() is True


def test_manifest_store_round_trips_equal_aggregate() -> None:
    store = FakeManifestStore()
    manifest = _sample_manifest()
    store.write(manifest)
    read_back = store.read()
    assert len(read_back.references) == 1
    only = read_back.references[0]
    assert str(only.name) == "json-spec"
    assert str(only.role) == "json-mapping"
    assert only.source == "acme/json-spec"
    assert only.spec.kind is RefKind.SEMVER
    assert only.spec.value == "^2.1.0"
    assert only.subdirectory == "docs"
    assert read_back.by_name(RefName("json-spec")) is only


# --------------------------------------------------------------------------- LockfileStore


def test_lockfile_store_satisfies_protocol() -> None:
    assert isinstance(FakeLockfileStore(), LockfileStore)


def test_lockfile_store_starts_absent_and_reads_empty() -> None:
    store = FakeLockfileStore()
    assert store.exists() is False
    fresh = store.read()
    assert isinstance(fresh, Lockfile)
    assert len(fresh) == 0
    assert fresh.lockfile_version == CURRENT_LOCKFILE_VERSION


def test_lockfile_store_exists_flips_after_write() -> None:
    store = FakeLockfileStore()
    assert store.exists() is False
    store.write(_sample_lockfile())
    assert store.exists() is True


def test_lockfile_store_round_trips_equal_aggregate() -> None:
    store = FakeLockfileStore()
    lock = _sample_lockfile()
    store.write(lock)
    read_back = store.read()
    assert len(read_back) == 1
    entry = read_back.get(RefName("json-spec"))
    assert entry is not None
    assert entry.ref_type is RefKind.SEMVER
    assert entry.resolved == "2.1.4"
    assert entry.pin.commit.value == _COMMIT_HEX
    assert entry.pin.content_hash.value == "sha256:" + "c" * 64
    assert entry.confirmed_through is None


# --------------------------------------------------------------------------- ContentStore


def test_content_store_satisfies_protocol() -> None:
    assert isinstance(FakeContentStore(), ContentStore)


def test_content_store_materialize_then_read_returns_same_entries() -> None:
    store = FakeContentStore()
    name = RefName("json-spec")
    tree = _sample_tree()
    store.materialize(name, "2.1.4", tree)
    read_back = store.read_tree(name, "2.1.4")
    assert len(read_back) == 2
    assert read_back[0] == TreeEntry(path="a.md", mode=0o100644, blob=b"hello\n")
    assert read_back[1] == TreeEntry(path="b/c.md", mode=0o100644, blob=b"world\n")


def test_content_store_verify_true_for_matching_tree() -> None:
    store = FakeContentStore()
    name = RefName("json-spec")
    tree = _sample_tree()
    store.materialize(name, "2.1.4", tree)
    expected = compute_content_hash(tree)
    assert store.verify(name, "2.1.4", expected) is True


def test_content_store_verify_false_for_tampered_tree() -> None:
    store = FakeContentStore()
    name = RefName("json-spec")
    original = _sample_tree()
    expected = compute_content_hash(original)
    tampered = [
        TreeEntry(path="a.md", mode=0o100644, blob=b"HACKED\n"),
        TreeEntry(path="b/c.md", mode=0o100644, blob=b"world\n"),
    ]
    store.materialize(name, "2.1.4", tampered)
    assert store.verify(name, "2.1.4", expected) is False


def test_content_store_verify_false_for_missing_reference() -> None:
    store = FakeContentStore()
    expected = compute_content_hash(_sample_tree())
    assert store.verify(RefName("absent"), "1.0.0", expected) is False


def test_content_store_remove_clears_all_labels_for_name() -> None:
    store = FakeContentStore()
    name = RefName("json-spec")
    store.materialize(name, "2.1.3", _sample_tree())
    store.materialize(name, "2.1.4", _sample_tree())
    store.remove(name)
    expected = compute_content_hash(_sample_tree())
    assert store.verify(name, "2.1.3", expected) is False
    assert store.verify(name, "2.1.4", expected) is False


def test_content_store_read_tree_is_isolated_copy() -> None:
    store = FakeContentStore()
    name = RefName("json-spec")
    store.materialize(name, "2.1.4", _sample_tree())
    read_back = store.read_tree(name, "2.1.4")
    read_back.append(TreeEntry(path="x.md", mode=0o100644, blob=b"x"))
    # Mutating the returned list must not corrupt the store.
    assert len(store.read_tree(name, "2.1.4")) == 2


# --------------------------------------------------------------------------- AgentFileStore


def test_agent_file_store_satisfies_protocol() -> None:
    assert isinstance(FakeAgentFileStore(), AgentFileStore)


def test_agent_file_store_records_last_block() -> None:
    store = FakeAgentFileStore()
    assert store.last_block is None
    store.write_inventory_block("## references\n- json-spec")
    assert store.last_block == "## references\n- json-spec"
    store.write_inventory_block("## references\n- updated")
    assert store.last_block == "## references\n- updated"


def test_agent_file_store_ensure_claude_import_sets_flag() -> None:
    store = FakeAgentFileStore()
    assert store.claude_imported is False
    store.ensure_claude_import()
    assert store.claude_imported is True
