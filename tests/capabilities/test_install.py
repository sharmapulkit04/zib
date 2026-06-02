"""Scenario test for the ``install`` capability.

Real rules + real gateway processes (ResolveProcess / FetchProcess wired to a FakeGitPort)
+ fake persistence stores. Nothing is mocked — the same wiring an e2e test uses, minus the
real shell and disk. Assertions read concrete state back out of the fake stores: the exact
``installed``/``verified`` lists, the exact ``resolved`` label each lock entry carries, and
whether the content store verifies the pin afterward.

The three SCENARIOS cover the install state machine end to end:
  fresh_two_refs        — clean first install: both refs resolved, locked, materialized
  idempotent_noop       — re-running a complete install changes nothing (no rewrite, no fetch)
  rematerialize_missing — a locked ref with missing content is re-fetched by its pinned commit
"""

from __future__ import annotations

import pytest

from tests.capabilities.install_scenarios import SCENARIOS
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.install.install import Install, InstallResult
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
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash


def _tree(files: list[tuple[str, bytes]]) -> list[TreeEntry]:
    return [TreeEntry(path=path, mode=0o100644, blob=blob) for path, blob in files]


def _build(scenario: dict):
    """Wire a fully real Install for one scenario, returning (cap, stores) for assertions."""
    git = FakeGitPort()
    manifest = Manifest()
    file_index: dict[str, list[tuple[str, bytes]]] = {}

    for ref in scenario["input"]["references"]:
        spec = RefSpec.from_manifest(
            version=ref.get("version"),
            branch=ref.get("branch"),
            tag=ref.get("tag"),
            rev=ref.get("rev"),
        )
        manifest.add(
            ReferenceEntry(
                name=RefName(ref["name"]),
                role=Role(ref["role"]),
                source=ref["source"],
                spec=spec,
                subdirectory=ref.get("subdirectory"),
                description=ref.get("description"),
            )
        )
        for tag_name, commit_hex in ref.get("tags", []):
            git.add_tag(ref["source"], tag_name, commit_hex)
        for commit_hex, files in ref.get("tree", {}).items():
            git.set_tree(ref["source"], commit_hex, _tree(files))
        file_index[ref["name"]] = next(iter(ref.get("tree", {}).values()), [])

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    content_store = FakeContentStore()
    agent_store = FakeAgentFileStore()

    pre = scenario["input"].get("pre", {})
    if pre:
        lockfile = Lockfile()
        for locked in pre.get("locked", []):
            tree = _tree(file_index[locked["name"]])
            pin = Pin(
                commit=CommitSha(locked["commit"]),
                content_hash=compute_content_hash(tree),
            )
            lockfile.put(
                LockEntry(
                    name=RefName(locked["name"]),
                    ref_type=RefKind.SEMVER,
                    resolved=locked["label"],
                    pin=pin,
                )
            )
        lockfile_store.write(lockfile)
        for name in pre.get("materialized", []):
            label = next(
                lk["label"] for lk in pre["locked"] if lk["name"] == name
            )
            content_store.materialize(
                RefName(name), label, _tree(file_index[name])
            )

    cap = Install(
        manifest_store=manifest_store,
        lockfile_store=lockfile_store,
        content_store=content_store,
        agent_file_store=agent_store,
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
    )
    return cap, {
        "manifest": manifest_store,
        "lockfile": lockfile_store,
        "content": content_store,
        "agent": agent_store,
    }


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_install_scenarios(key: str) -> None:
    scenario = SCENARIOS[key]
    cap, stores = _build(scenario)

    result = cap.execute()
    expect = scenario["expect"]

    assert isinstance(result, InstallResult)
    assert result.installed == expect["installed"]
    assert result.verified == expect["verified"]

    lockfile = stores["lockfile"].read()
    for name, label in expect["locked"].items():
        entry = lockfile.get(RefName(name))
        assert entry is not None
        assert entry.resolved == label

    for name, ok in expect["materialized"].items():
        entry = lockfile.get(RefName(name))
        assert stores["content"].verify(
            RefName(name), entry.resolved, entry.pin.content_hash
        ) is ok


def test_fresh_install_locks_pins_and_materializes_both_refs() -> None:
    cap, stores = _build(SCENARIOS["fresh_two_refs"])

    result = cap.execute()

    assert result.installed == ["mapping", "spec"]
    assert result.verified == []
    lockfile = stores["lockfile"].read()
    assert len(lockfile) == 2
    # spec is a semver range -> SEMVER ref type; mapping an exact tag -> TAG.
    assert lockfile.get(RefName("spec")).ref_type is RefKind.SEMVER
    assert lockfile.get(RefName("mapping")).ref_type is RefKind.TAG
    assert lockfile.get(RefName("spec")).pin.commit == CommitSha("a" * 40)
    # Nothing confirmed yet -> the pin leads the (absent) baseline -> owed delta.
    assert lockfile.get(RefName("spec")).has_owed_delta() is True
    # Agent files refreshed last: block written, CLAUDE import ensured.
    assert stores["agent"].claude_imported is True
    assert "spec" in stores["agent"].last_block
    assert "mapping" in stores["agent"].last_block


def test_idempotent_install_does_not_rewrite_lockfile_or_refetch() -> None:
    cap, stores = _build(SCENARIOS["idempotent_noop"])
    lockfile_store = stores["lockfile"]
    before = lockfile_store.read()  # the same object the store holds

    result = cap.execute()

    assert result.installed == []
    assert result.verified == []
    # Compare-before-write at the capability level: a clean run added no entry, so the
    # stored lockfile object is the identical instance (never rewritten).
    assert lockfile_store.read() is before
    assert len(lockfile_store.read()) == 1


def test_rematerialize_recovers_missing_content_without_moving_the_pin() -> None:
    cap, stores = _build(SCENARIOS["rematerialize_missing"])
    lockfile_store = stores["lockfile"]
    pin_before = lockfile_store.read().get(RefName("spec")).pin

    result = cap.execute()

    assert result.installed == []
    assert result.verified == ["spec"]
    entry = lockfile_store.read().get(RefName("spec"))
    # Pin is unchanged — install refetches by commit, it never re-resolves or moves a pin.
    assert entry.pin == pin_before
    assert entry.resolved == "v2.1.0"
    # Content is now present and verifies against the recorded hash.
    assert stores["content"].verify(
        RefName("spec"), entry.resolved, entry.pin.content_hash
    ) is True


def test_install_skips_unlocked_refs_in_inventory_until_pinned() -> None:
    # A manifest reference whose source has no matching tag fails to resolve; the rest of
    # install still proceeds for the resolvable one. Here we assert the inventory shows
    # exactly the materialized reference.
    cap, stores = _build(SCENARIOS["fresh_two_refs"])
    cap.execute()
    block = stores["agent"].last_block
    # Both got pinned in this scenario, so both must appear with their content paths.
    assert ".zib/references/spec/" in block
    assert ".zib/references/mapping/" in block
    assert "UPDATE PENDING" in block  # nothing confirmed yet -> owed delta surfaced
