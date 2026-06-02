"""Scenario tests for the swap_reference capability.

Real rules + real gateway processes (ResolveProcess / FetchProcess) wired to a FakeGitPort
and the validated fake stores — no mocking of rules (CLAUDE.md). Each test asserts CONCRETE
outcomes read back through the fake stores: the old reference is gone from manifest, lockfile
and content; the new one is present under the inherited role with a RESET baseline (owed
delta True); and the agent inventory block is refreshed.
"""

from __future__ import annotations

import pytest

from tests.capabilities.swap_reference_scenarios import SCENARIOS
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.swap_reference.swap_reference import (
    SwapReference,
    SwapResult,
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
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash

OLD_COMMIT = "a" * 40
NEW_COMMIT = "b" * 40


def _spec_for(new: dict) -> RefSpec:
    if "version" in new:
        return RefSpec.from_manifest(version=new["version"])
    return RefSpec.from_manifest(tag=new["tag"])


def _wire(scenario: dict):
    """Build a fully wired SwapReference plus its fake stores, seeded for the scenario."""
    inp = scenario["input"]
    old, new = inp["old"], inp["new"]

    git = FakeGitPort()

    # --- seed the OLD source so its content can be materialized at setup time ---
    git.add_tag(old["source"], old["tag"], OLD_COMMIT)
    git.set_tree(
        old["source"],
        OLD_COMMIT,
        [TreeEntry(f"{old['name']}.md", 0o100644, b"old reference body\n")],
    )

    # --- seed the NEW source: tag(s) + the tree it resolves to ---
    if "available_tags" in new:
        # Non-resolved tags point at a decoy commit; the resolved tag points at NEW_COMMIT.
        for tag in new["available_tags"]:
            commit = NEW_COMMIT if tag == new["resolves_to"] else ("c" * 40)
            git.add_tag(new["source"], tag, commit)
    else:
        git.add_tag(new["source"], new["tag"], NEW_COMMIT)
    git.set_tree(
        new["source"],
        NEW_COMMIT,
        [TreeEntry(f"{new['name']}.md", 0o100644, b"new reference body - different\n")],
    )

    resolve = ResolveProcess(git)
    fetch = FetchProcess(git)

    manifest_store = FakeManifestStore()
    lockfile_store = FakeLockfileStore()
    content_store = FakeContentStore()
    agent_store = FakeAgentFileStore()

    # --- seed manifest + lockfile + content with the OLD reference, CONFIRMED through its
    #     pin (so we prove the baseline truly goes away on removal, not lingers) ---
    old_name = RefName(old["name"])
    old_tree = [TreeEntry(f"{old['name']}.md", 0o100644, b"old reference body\n")]
    old_hash = compute_content_hash(old_tree)
    old_pin = Pin(commit=CommitSha(OLD_COMMIT), content_hash=old_hash)

    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=old_name,
            role=Role(inp["role"]),
            source=old["source"],
            spec=RefSpec.from_manifest(tag=old["tag"]),
        )
    )
    lockfile = Lockfile()
    lockfile.put(
        LockEntry(
            name=old_name,
            ref_type=RefKind.TAG,
            resolved=old["tag"],
            pin=old_pin,
            confirmed_through=old_pin,  # old ref was fully confirmed
        )
    )
    manifest_store.write(manifest)
    lockfile_store.write(lockfile)
    content_store.materialize(old_name, old["tag"], old_tree)

    cap = SwapReference(
        manifest_store=manifest_store,
        lockfile_store=lockfile_store,
        content_store=content_store,
        agent_file_store=agent_store,
        resolve_process=resolve,
        fetch_process=fetch,
    )
    return cap, manifest_store, lockfile_store, content_store, agent_store


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_swap_scenarios(key):
    scenario = SCENARIOS[key]
    inp, expect = scenario["input"], scenario["expect"]
    old, new = inp["old"], inp["new"]

    cap, manifest_store, lockfile_store, content_store, agent_store = _wire(scenario)

    result = cap.execute(
        role=inp["role"],
        new_name=new["name"],
        new_source=new["source"],
        new_spec=_spec_for(new),
    )

    # --- result object ---
    assert isinstance(result, SwapResult)
    assert result.role == expect["result_role"]
    assert result.removed_name == expect["result_removed_name"]
    assert result.added_name == expect["result_added_name"]

    manifest = manifest_store.read()
    lockfile = lockfile_store.read()

    # --- old reference fully gone ---
    assert (manifest.by_name(RefName(old["name"])) is not None) == expect[
        "old_in_manifest"
    ]
    assert (lockfile.get(RefName(old["name"])) is not None) == expect["old_in_lockfile"]
    assert len(manifest.references) == expect["manifest_count"]
    assert len(lockfile) == expect["lockfile_count"]

    # --- new reference present under the inherited role ---
    new_entry = manifest.by_name(RefName(new["name"]))
    assert (new_entry is not None) == expect["new_in_manifest"]
    assert str(new_entry.role) == expect["new_role"]

    new_lock = lockfile.get(RefName(new["name"]))
    assert new_lock.resolved == expect["new_resolved"]
    assert new_lock.ref_type.value == expect["new_ref_type"]
    assert new_lock.pin.commit == CommitSha(NEW_COMMIT)

    # --- baseline RESET → owed delta True, nothing confirmed ---
    assert new_lock.has_owed_delta() is expect["new_owed_delta"]
    assert (new_lock.confirmed_through is None) is expect[
        "new_confirmed_through_is_none"
    ]

    # --- role preserved: exactly the new reference fills the role now ---
    filling = manifest.by_role(Role(inp["role"]))
    assert len(filling) == 1
    assert str(filling[0].name) == new["name"]

    # --- agent inventory refreshed ---
    body = agent_store.last_block
    assert body is not None
    assert (new["name"] in body) == expect["inventory_mentions_new"]
    assert (old["name"] in body) == expect["inventory_mentions_old"]
    assert "UPDATE PENDING" in body  # the reset baseline must surface as a pending delta


def test_swap_removes_old_content_and_materializes_new():
    """Concrete content-store assertions: old name purged, new name verifiable at its label."""
    scenario = SCENARIOS["swap_within_role"]
    inp, new, old = scenario["input"], scenario["input"]["new"], scenario["input"]["old"]

    cap, _, _, content_store, _ = _wire(scenario)
    cap.execute(
        role=inp["role"],
        new_name=new["name"],
        new_source=new["source"],
        new_spec=_spec_for(new),
    )

    # old content gone — read_tree raises KeyError for a purged reference.
    with pytest.raises(KeyError):
        content_store.read_tree(RefName(old["name"]), old["tag"])

    # new content present and verifiable against its freshly computed hash at its label.
    new_tree = content_store.read_tree(RefName(new["name"]), new["tag"])
    assert len(new_tree) == 1
    assert new_tree[0].path == "moshi.md"
    expected_hash = compute_content_hash(new_tree)
    assert content_store.verify(RefName(new["name"]), new["tag"], expected_hash) is True
    assert isinstance(expected_hash, ContentHash)


def test_swap_errors_when_role_unfilled():
    """No reference fills the role → ValueError, nothing written."""
    git = FakeGitPort()
    git.add_tag("acme/moshi", "v1.15.0", NEW_COMMIT)
    git.set_tree("acme/moshi", NEW_COMMIT, [TreeEntry("moshi.md", 0o100644, b"x\n")])

    manifest_store = FakeManifestStore()
    lockfile_store = FakeLockfileStore()
    agent_store = FakeAgentFileStore()
    cap = SwapReference(
        manifest_store=manifest_store,
        lockfile_store=lockfile_store,
        content_store=FakeContentStore(),
        agent_file_store=agent_store,
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
    )

    with pytest.raises(ValueError, match="no reference fills role"):
        cap.execute(
            role="json-mapping",
            new_name="moshi",
            new_source="acme/moshi",
            new_spec=RefSpec.from_manifest(tag="v1.15.0"),
        )
    # nothing leaked to the agent files.
    assert agent_store.last_block is None


def test_swap_errors_when_role_ambiguous():
    """Two references share the role → ValueError naming the count; nothing written."""
    git = FakeGitPort()
    git.add_tag("acme/moshi", "v1.15.0", NEW_COMMIT)
    git.set_tree("acme/moshi", NEW_COMMIT, [TreeEntry("moshi.md", 0o100644, b"x\n")])

    pin = Pin(commit=CommitSha(OLD_COMMIT), content_hash=ContentHash("sha256:" + "0" * 64))

    manifest = Manifest()
    for nm in ("jackson", "gson"):
        manifest.add(
            ReferenceEntry(
                name=RefName(nm),
                role=Role("json-mapping"),
                source=f"acme/{nm}",
                spec=RefSpec.from_manifest(tag="v1.0.0"),
            )
        )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    agent_store = FakeAgentFileStore()

    cap = SwapReference(
        manifest_store=manifest_store,
        lockfile_store=FakeLockfileStore(),
        content_store=FakeContentStore(),
        agent_file_store=agent_store,
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
    )

    with pytest.raises(ValueError, match="is filled by 2 references"):
        cap.execute(
            role="json-mapping",
            new_name="moshi",
            new_source="acme/moshi",
            new_spec=RefSpec.from_manifest(tag="v1.15.0"),
        )
    assert agent_store.last_block is None
