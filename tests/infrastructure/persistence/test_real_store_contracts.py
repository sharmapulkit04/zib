"""Re-run the persistence port CONTRACT tests against the REAL adapters.

CLAUDE.md: the same contract any implementation must satisfy is re-run against the real
technology. These bind the real stores to ``tmp_path`` and assert the documented behavior —
protocol conformance, round-trip equality, materialize/verify/remove, and the managed-block /
import behavior — exactly as the fakes are asserted in ``tests/ports/persistence``.
"""

from __future__ import annotations

from pathlib import Path

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import CURRENT_LOCKFILE_VERSION, Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.entities.shared.value_objects import (
    SYMLINK_MODE,
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
from zib.infrastructure.agent_files.agent_file_store import MarkdownAgentFileStore
from zib.infrastructure.persistence.content_store import FileContentStore
from zib.infrastructure.persistence.lockfile_store import TomlLockfileStore
from zib.infrastructure.persistence.manifest_store import TomlManifestStore

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
    pin = Pin(commit=CommitSha(_COMMIT_HEX), content_hash=ContentHash("sha256:" + "c" * 64))
    entry = LockEntry(
        name=RefName("json-spec"), ref_type=RefKind.SEMVER, resolved="2.1.4", pin=pin
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


def test_real_manifest_store_satisfies_protocol(tmp_path: Path) -> None:
    assert isinstance(TomlManifestStore(tmp_path), ManifestStore)


def test_real_manifest_store_starts_absent_and_reads_empty(tmp_path: Path) -> None:
    store = TomlManifestStore(tmp_path)
    assert store.exists() is False
    fresh = store.read()
    assert fresh.references == []
    assert fresh.poll is None


def test_real_manifest_store_exists_flips_after_write(tmp_path: Path) -> None:
    store = TomlManifestStore(tmp_path)
    assert store.exists() is False
    store.write(_sample_manifest())
    assert store.exists() is True


def test_real_manifest_store_round_trips_equal_aggregate(tmp_path: Path) -> None:
    store = TomlManifestStore(tmp_path)
    store.write(_sample_manifest())
    read_back = store.read()
    only = read_back.references[0]
    assert str(only.name) == "json-spec"
    assert str(only.role) == "json-mapping"
    assert only.source == "acme/json-spec"
    assert only.spec.kind is RefKind.SEMVER
    assert only.spec.value == "^2.1.0"
    assert only.subdirectory == "docs"


def test_real_manifest_store_preserves_user_comments(tmp_path: Path) -> None:
    path = tmp_path / "zib.toml"
    path.write_text(
        "# my project references\n\n"
        '[[reference]]\nname = "hex"\nrole = "architecture"\n'
        'source = "/x"\nbranch = "main"\n',
        encoding="utf-8",
    )
    store = TomlManifestStore(tmp_path)
    manifest = store.read()
    # Add a second reference and write back.
    manifest.add(
        ReferenceEntry(
            name=RefName("json"),
            role=Role("json"),
            source="/y",
            spec=RefSpec.from_manifest(tag="v1.0.0"),
        )
    )
    store.write(manifest)
    text = path.read_text(encoding="utf-8")
    assert "# my project references" in text  # comment preserved
    assert 'branch = "main"' in text
    assert 'tag = "v1.0.0"' in text


def test_real_manifest_store_write_is_idempotent(tmp_path: Path) -> None:
    store = TomlManifestStore(tmp_path)
    store.write(_sample_manifest())
    first = (tmp_path / "zib.toml").read_text(encoding="utf-8")
    mtime = (tmp_path / "zib.toml").stat().st_mtime_ns
    store.write(store.read())
    assert (tmp_path / "zib.toml").read_text(encoding="utf-8") == first
    assert (tmp_path / "zib.toml").stat().st_mtime_ns == mtime  # untouched


# --------------------------------------------------------------------------- LockfileStore


def test_real_lockfile_store_satisfies_protocol(tmp_path: Path) -> None:
    assert isinstance(TomlLockfileStore(tmp_path), LockfileStore)


def test_real_lockfile_store_starts_absent_and_reads_empty(tmp_path: Path) -> None:
    store = TomlLockfileStore(tmp_path)
    assert store.exists() is False
    fresh = store.read()
    assert len(fresh) == 0
    assert fresh.lockfile_version == CURRENT_LOCKFILE_VERSION


def test_real_lockfile_store_round_trips_equal_aggregate(tmp_path: Path) -> None:
    store = TomlLockfileStore(tmp_path)
    store.write(_sample_lockfile())
    read_back = store.read()
    entry = read_back.get(RefName("json-spec"))
    assert entry is not None
    assert entry.ref_type is RefKind.SEMVER
    assert entry.resolved == "2.1.4"
    assert entry.pin.commit.value == _COMMIT_HEX
    assert entry.pin.content_hash.value == "sha256:" + "c" * 64
    assert entry.confirmed_through is None


def test_real_lockfile_store_round_trips_confirmed_baseline(tmp_path: Path) -> None:
    store = TomlLockfileStore(tmp_path)
    lock = _sample_lockfile()
    entry = lock.get(RefName("json-spec"))
    entry.confirm(Pin(CommitSha(_OTHER_HEX), ContentHash("sha256:" + "d" * 64)))
    store.write(lock)
    back = store.read().get(RefName("json-spec"))
    assert back.confirmed_through is not None
    assert back.confirmed_through.commit.value == _OTHER_HEX


def test_real_lockfile_store_write_is_idempotent(tmp_path: Path) -> None:
    store = TomlLockfileStore(tmp_path)
    store.write(_sample_lockfile())
    mtime = (tmp_path / "zib.lock").stat().st_mtime_ns
    store.write(store.read())
    assert (tmp_path / "zib.lock").stat().st_mtime_ns == mtime


# --------------------------------------------------------------------------- ContentStore


def test_real_content_store_satisfies_protocol(tmp_path: Path) -> None:
    assert isinstance(FileContentStore(tmp_path), ContentStore)


def test_real_content_store_materialize_then_read(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("json-spec")
    store.materialize(name, "2.1.4", _sample_tree())
    read_back = store.read_tree(name, "2.1.4")
    assert TreeEntry(path="a.md", mode=0o100644, blob=b"hello\n") in read_back
    assert TreeEntry(path="b/c.md", mode=0o100644, blob=b"world\n") in read_back


def test_real_content_store_verify_true_for_matching(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("json-spec")
    tree = _sample_tree()
    store.materialize(name, "2.1.4", tree)
    assert store.verify(name, "2.1.4", compute_content_hash(tree)) is True


def test_real_content_store_verify_false_for_tampered(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("json-spec")
    expected = compute_content_hash(_sample_tree())
    store.materialize(
        name, "2.1.4",
        [TreeEntry(path="a.md", mode=0o100644, blob=b"HACKED\n"),
         TreeEntry(path="b/c.md", mode=0o100644, blob=b"world\n")],
    )
    assert store.verify(name, "2.1.4", expected) is False


def test_real_content_store_verify_false_for_missing(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    assert store.verify(RefName("absent"), "1.0.0", compute_content_hash(_sample_tree())) is False


def test_real_content_store_remove_clears_all_labels(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("json-spec")
    store.materialize(name, "2.1.3", _sample_tree())
    store.materialize(name, "2.1.4", _sample_tree())
    store.remove(name)
    expected = compute_content_hash(_sample_tree())
    assert store.verify(name, "2.1.3", expected) is False
    assert store.verify(name, "2.1.4", expected) is False


def test_real_content_store_read_tree_is_isolated_copy(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("json-spec")
    store.materialize(name, "2.1.4", _sample_tree())
    read_back = store.read_tree(name, "2.1.4")
    read_back.append(TreeEntry(path="x.md", mode=0o100644, blob=b"x"))
    assert len(store.read_tree(name, "2.1.4")) == 2


def test_real_content_store_preserves_executable_and_symlink_modes(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("scripts")
    tree = [
        TreeEntry(path="run.sh", mode=0o100755, blob=b"#!/bin/sh\necho hi\n"),
        TreeEntry(path="link", mode=SYMLINK_MODE, blob=b"run.sh"),
    ]
    store.materialize(name, "v1", tree)
    assert store.verify(name, "v1", compute_content_hash(tree)) is True
    back = {e.path: e for e in store.read_tree(name, "v1")}
    assert back["run.sh"].mode == 0o100755
    assert back["link"].mode == SYMLINK_MODE
    assert back["link"].blob == b"run.sh"


def test_real_content_store_handles_labels_with_path_unsafe_chars(tmp_path: Path) -> None:
    store = FileContentStore(tmp_path)
    name = RefName("spec")
    tree = _sample_tree()
    store.materialize(name, "^2.1.0", tree)
    assert store.verify(name, "^2.1.0", compute_content_hash(tree)) is True


# --------------------------------------------------------------------------- AgentFileStore


def test_real_agent_file_store_satisfies_protocol(tmp_path: Path) -> None:
    assert isinstance(MarkdownAgentFileStore(tmp_path), AgentFileStore)


def test_real_agent_file_store_writes_block_and_round_trips(tmp_path: Path) -> None:
    store = MarkdownAgentFileStore(tmp_path)
    store.write_inventory_block("## refs\n- hex")
    text = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- zib:begin -->" in text
    assert "## refs\n- hex" in text
    assert "<!-- zib:end -->" in text
    # Rewriting replaces only the interior.
    store.write_inventory_block("## refs\n- updated")
    text2 = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "- updated" in text2
    assert "- hex" not in text2


def test_real_agent_file_store_preserves_text_outside_markers(tmp_path: Path) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text(
        "# Agents\n\nMy own prose.\n\n<!-- zib:begin -->\nold\n<!-- zib:end -->\n\nMore prose.\n",
        encoding="utf-8",
    )
    MarkdownAgentFileStore(tmp_path).write_inventory_block("new body")
    text = path.read_text(encoding="utf-8")
    assert "My own prose." in text
    assert "More prose." in text
    assert "new body" in text
    assert "old" not in text


def test_real_agent_file_store_ensure_claude_import(tmp_path: Path) -> None:
    store = MarkdownAgentFileStore(tmp_path)
    store.ensure_claude_import()
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "@AGENTS.md" in text


def test_real_agent_file_store_ensure_claude_import_is_idempotent(tmp_path: Path) -> None:
    store = MarkdownAgentFileStore(tmp_path)
    store.ensure_claude_import()
    first = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    store.ensure_claude_import()
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == first
    assert first.count("@AGENTS.md") == 1
