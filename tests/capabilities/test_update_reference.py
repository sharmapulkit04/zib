"""Scenario tests for the UpdateReference capability.

Real rules + real gateway processes (ResolveProcess / FetchProcess / NotesProcess)
wired to the validated FakeGitPort and the fake persistence stores. Nothing is
mocked — the scenarios prove orchestration and the conformance invariant through
actual store state (CLAUDE.md: capabilities are tested by scenarios, not unit tests).
"""

from __future__ import annotations

import pytest

from zib.core.capabilities.update_reference.update_reference import UpdateReference
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
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.port.git_port import GitCommit
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.rules.computation.delta.delta import Magnitude

from tests.capabilities.update_reference_scenarios import SCENARIOS
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)


def _file(path: str, line_count: int) -> "object":
    from zib.core.entities.shared.value_objects import TreeEntry

    body = "".join(f"line{i}\n" for i in range(line_count)).encode()
    return TreeEntry(path=path, mode=0o100644, blob=body)


def _spec_from(spec: tuple[str, str]) -> RefSpec:
    kind, value = spec
    return RefSpec.from_manifest(**{kind: value})


def _wire(inp: dict):
    """Build the full (capability, stores) world from a scenario input."""
    source = inp["source"]
    name = inp["name"]

    git = FakeGitPort()
    for tag_name, commit_hex in inp["tags"]:
        git.add_tag(source, tag_name, commit_hex)
    if inp["branch"] is not None:
        branch_name, commit_hex = inp["branch"]
        git.set_branch(source, branch_name, commit_hex)

    old_hex, _ = inp["pinned"]
    git.add_rev(source, old_hex)
    git.set_tree(source, old_hex, [_file(p, n) for p, n in inp["from_tree"]])

    # The resolved (new) commit: highest tag in range, or the branch tip.
    if inp["branch"] is not None:
        new_hex = inp["branch"][1]
    else:
        new_hex = inp["tags"][-1][1]
    git.set_tree(source, new_hex, [_file(p, n) for p, n in inp["to_tree"]])
    git.set_diff(source, old_hex, new_hex, inp["diff"])
    git.set_log(
        source,
        old_hex,
        new_hex,
        [GitCommit(commit=CommitSha(new_hex), subject="update", body="body")],
    )
    if inp["to_tag"] is not None and inp["tag_message"] is not None:
        git.set_tag_message(source, inp["to_tag"], inp["tag_message"])

    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName(name),
            role=Role(inp["role"]),
            source=source,
            spec=_spec_from(inp["spec"]),
            description=inp["description"],
        )
    )

    lockfile = Lockfile()
    pin = Pin(CommitSha(old_hex), ContentHash(inp["pinned"][1]))
    confirmed = (
        Pin(CommitSha(inp["confirmed"][0]), ContentHash(inp["confirmed"][1]))
        if inp["confirmed"] is not None
        else None
    )
    lockfile.put(
        LockEntry(
            name=RefName(name),
            ref_type=_spec_from(inp["spec"]).kind,
            resolved=inp["seed_resolved"],
            pin=pin,
            confirmed_through=confirmed,
        )
    )

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    content_store = FakeContentStore()
    agent_file_store = FakeAgentFileStore()

    cap = UpdateReference(
        manifest_store,
        lockfile_store,
        content_store,
        agent_file_store,
        ResolveProcess(git),
        FetchProcess(git),
        NotesProcess(git),
    )
    return cap, manifest_store, lockfile_store, content_store, agent_file_store


@pytest.mark.parametrize("key", list(SCENARIOS.keys()))
def test_scenarios(key: str) -> None:
    sc = SCENARIOS[key]
    inp, expect = sc["input"], sc["expect"]
    cap, _, lockfile_store, content_store, agent_file_store = _wire(inp)

    result = cap.execute(inp["name"])

    assert result.name == inp["name"]
    assert result.up_to_date is expect["up_to_date"]
    assert result.old_commit == expect["old_commit"]
    assert result.new_commit == expect["new_commit"]

    if expect["magnitude"] is None:
        assert result.magnitude is None
        assert result.delta is None
    else:
        assert result.magnitude is Magnitude(expect["magnitude"])
        assert result.delta is not None
        assert result.delta.magnitude is Magnitude(expect["magnitude"])
        assert result.delta.tag_notes == expect["tag_notes"]

    # Observable lock state — the conformance invariant lives here.
    entry = lockfile_store.read().get(RefName(inp["name"]))
    assert entry is not None
    assert entry.resolved == expect["resolved_label"]
    assert entry.ref_type is RefKind(expect["ref_type"])
    assert entry.pin.commit == CommitSha(expect["pin_commit"])
    assert entry.confirmed_through is not None
    assert entry.confirmed_through.commit == CommitSha(expect["confirmed_commit"])
    assert entry.has_owed_delta() is expect["has_owed_delta"]

    # Agent-facing inventory block was refreshed and carries (or not) the pending flag.
    body = agent_file_store.last_block
    if expect["up_to_date"]:
        assert body is None  # no mutation → no block rewrite at all
        assert content_store.read_tree  # store untouched (no materialize call)
    else:
        assert body is not None
        assert ("UPDATE PENDING" in body) is expect["inventory_has_update_pending"]
        # Content was materialized at the NEW label and verifies against the new pin.
        assert content_store.verify(
            RefName(inp["name"]), expect["resolved_label"], entry.pin.content_hash
        )


def test_up_to_date_leaves_pin_and_content_untouched() -> None:
    sc = SCENARIOS["already_newest_is_up_to_date"]
    cap, manifest_store, lockfile_store, content_store, agent_file_store = _wire(
        sc["input"]
    )
    pin_before = lockfile_store.read().get(RefName("spec")).pin

    result = cap.execute("spec")

    assert result.up_to_date is True
    # Identity: the very same pin object is still there (no repin happened).
    assert lockfile_store.read().get(RefName("spec")).pin is pin_before
    assert agent_file_store.last_block is None
    # Nothing materialized for a no-op update.
    with pytest.raises(KeyError):
        content_store.read_tree(RefName("spec"), "v2.1.0")


def test_repin_never_touches_confirmed_through() -> None:
    sc = SCENARIOS["semver_update_repins_and_owes_delta"]
    cap, _, lockfile_store, _, _ = _wire(sc["input"])
    confirmed_before = lockfile_store.read().get(RefName("spec")).confirmed_through

    cap.execute("spec")

    confirmed_after = lockfile_store.read().get(RefName("spec")).confirmed_through
    assert confirmed_after == confirmed_before
    assert confirmed_after.commit == CommitSha("1" * 40)


def test_unknown_reference_raises() -> None:
    sc = SCENARIOS["semver_update_repins_and_owes_delta"]
    cap, _, _, _, _ = _wire(sc["input"])
    with pytest.raises(ValueError, match="not declared"):
        cap.execute("nope")


def test_declared_but_not_pinned_raises() -> None:
    sc = SCENARIOS["semver_update_repins_and_owes_delta"]
    cap, _, lockfile_store, _, _ = _wire(sc["input"])
    # Drop the lock entry but keep the manifest declaration.
    empty = Lockfile()
    lockfile_store.write(empty)
    with pytest.raises(ValueError, match="not pinned"):
        cap.execute("spec")


def test_branch_update_delta_carries_commit_log() -> None:
    sc = SCENARIOS["branch_tip_update_repins_no_tag_notes"]
    cap, _, _, _, _ = _wire(sc["input"])

    result = cap.execute("spec")

    assert result.up_to_date is False
    assert result.delta is not None
    assert len(result.delta.commits) == 1
    assert result.delta.commits[0].subject == "update"
    assert result.delta.tag_notes is None
