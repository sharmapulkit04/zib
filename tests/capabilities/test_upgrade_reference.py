"""Scenario tests for the upgrade_reference capability.

Real rules + real gateway processes (resolve / fetch / notes) wired to a ``FakeGitPort`` and
in-memory fake stores — NO mocking of rules (CLAUDE.md: a capability's test is the scenario
test). Each scenario asserts CONCRETE outcomes read back from the fakes: the rewritten
manifest constraint, the new pin commit + label, the magnitude, and the owed-delta flag.

The defining behaviors under test (solution spec §8 / §8.4 / §9):
  * upgrade replaces the manifest entry's spec FIRST (the only consume that edits zib.toml),
  * then resolves WITHIN the new spec (^3 → highest 3.x tag),
  * repins WITHOUT touching confirmed_through (owed delta stays True),
  * fetches + materializes the new tree, persists, and refreshes the agent block LAST,
  * surfaces a Delta whose range anchors on the confirmed baseline (or the prior pin when
    nothing is confirmed).
"""

from __future__ import annotations

import pytest

from tests.capabilities.upgrade_reference_scenarios import SCENARIOS, SOURCE, TAGS
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.upgrade_reference.upgrade_reference import (
    UpgradeReference,
    UpgradeResult,
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
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess


def _build(scenario: dict):
    """Wire one scenario: fresh git port + fake stores + a fully assembled capability.

    Returns ``(capability, manifest_store, lockfile_store, content_store, agent_store, name)``.
    """
    inp = scenario["input"]
    name = inp["name"]
    new_commit = scenario["expect"]["new_commit"]
    resolved_label = scenario["expect"]["resolved"]

    git = FakeGitPort()
    for tag_name, commit_hex in TAGS:
        git.add_tag(SOURCE, tag_name, commit_hex)

    # Baseline (from-side) tree sized to drive the churn ratio: one file whose blob carries
    # exactly ``baseline_tree_lines`` newlines (the notes process counts newlines).
    baseline_blob = ("x\n" * inp["baseline_tree_lines"]).encode("utf-8")
    git.set_tree(SOURCE, inp["confirmed_commit"] or inp["pinned_commit"],
                 [TreeEntry("spec.md", 0o100644, baseline_blob)])

    # The new pin's tree — what fetch materializes.
    git.set_tree(SOURCE, new_commit,
                 [TreeEntry("spec.md", 0o100644, b"the upgraded spec content\n")])

    # The diff is registered on the (delta_from, new_commit) pair the capability will query.
    delta_from = inp["confirmed_commit"] or inp["pinned_commit"]
    git.set_diff(SOURCE, delta_from, new_commit, inp["diff_text"])
    git.set_tag_message(SOURCE, resolved_label, scenario["expect"]["tag_notes"])

    # Seed the manifest with the OLD constraint and the lockfile with the current pin.
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName(name),
            role=Role("spec-driven-development"),
            source=SOURCE,
            spec=RefSpec(RefKind.SEMVER, inp["old_version"]),
            subdirectory=None,
            description="Our spec source of truth",
        )
    )

    confirmed = (
        Pin(CommitSha(inp["confirmed_commit"]), ContentHash("sha256:" + "1" * 64))
        if inp["confirmed_commit"] is not None
        else None
    )
    lockfile = Lockfile()
    lockfile.put(
        LockEntry(
            name=RefName(name),
            ref_type=RefKind.SEMVER,
            resolved=inp["pinned_label"],
            pin=Pin(CommitSha(inp["pinned_commit"]), ContentHash("sha256:" + "2" * 64)),
            confirmed_through=confirmed,
        )
    )

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    content_store = FakeContentStore()
    agent_store = FakeAgentFileStore()

    cap = UpgradeReference(
        manifest_store=manifest_store,
        lockfile_store=lockfile_store,
        content_store=content_store,
        agent_file_store=agent_store,
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
        notes_process=NotesProcess(git),
    )
    return cap, manifest_store, lockfile_store, content_store, agent_store, name


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_upgrade_scenarios(key: str) -> None:
    scenario = SCENARIOS[key]
    expect = scenario["expect"]
    new_spec = RefSpec(RefKind.SEMVER, expect["constraint_rewritten_to"])

    cap, manifest_store, lockfile_store, content_store, agent_store, name = _build(scenario)
    result = cap.execute(name, new_spec)

    # --- result object carries the concrete old/new pins + magnitude + delta -------------
    assert isinstance(result, UpgradeResult)
    assert result.name == RefName(name)
    assert result.old_commit == CommitSha(expect["old_commit"])
    assert result.new_commit == CommitSha(expect["new_commit"])
    assert result.magnitude == expect["magnitude"]
    assert result.delta.magnitude.value == expect["magnitude"]
    assert result.delta.diff_text == scenario["input"]["diff_text"]
    assert result.delta.tag_notes == expect["tag_notes"]

    # --- manifest constraint rewritten to the NEW spec (the upgrade-only edit) -----------
    entry = manifest_store.read().by_name(RefName(name))
    assert entry is not None
    assert entry.spec.kind is RefKind.SEMVER
    assert entry.spec.value == expect["constraint_rewritten_to"]
    # Every other manifest field is carried over verbatim.
    assert str(entry.role) == "spec-driven-development"
    assert entry.source == SOURCE
    assert entry.description == "Our spec source of truth"

    # --- lockfile re-pinned within the new spec; confirmed_through UNTOUCHED -------------
    locked = lockfile_store.read().get(RefName(name))
    assert locked is not None
    assert locked.resolved == expect["resolved"]
    assert locked.ref_type.value == expect["ref_type"]
    assert locked.pin.commit == CommitSha(expect["new_commit"])
    assert locked.has_owed_delta() is expect["owed_delta"]
    # The baseline is exactly what it was before — repin never advances it.
    if scenario["input"]["confirmed_commit"] is None:
        assert locked.confirmed_through is None
    else:
        assert locked.confirmed_through.commit == CommitSha(
            scenario["input"]["confirmed_commit"]
        )

    # --- content materialized under the new resolved label, hashing to the new pin -------
    assert content_store.verify(
        RefName(name), expect["resolved"], locked.pin.content_hash
    ) is True

    # --- agent files refreshed LAST: block carries the new version + the owed-delta line -
    assert agent_store.claude_imported is True
    assert agent_store.last_block is not None
    assert expect["resolved"] in agent_store.last_block
    assert "UPDATE PENDING" in agent_store.last_block


def test_upgrade_unknown_reference_raises() -> None:
    """Upgrading a name that was never added is a hard error (nothing to re-pin)."""
    cap = UpgradeReference(
        manifest_store=FakeManifestStore(),
        lockfile_store=FakeLockfileStore(),
        content_store=FakeContentStore(),
        agent_file_store=FakeAgentFileStore(),
        resolve_process=ResolveProcess(FakeGitPort()),
        fetch_process=FetchProcess(FakeGitPort()),
        notes_process=NotesProcess(FakeGitPort()),
    )
    with pytest.raises(KeyError):
        cap.execute("ghost", RefSpec(RefKind.SEMVER, "^3.0.0"))


def test_upgrade_pinned_but_not_in_manifest_raises() -> None:
    """A lock entry without a manifest entry can't be upgraded — manifest is checked first."""
    manifest_store = FakeManifestStore()
    manifest_store.write(Manifest())  # empty
    cap = UpgradeReference(
        manifest_store=manifest_store,
        lockfile_store=FakeLockfileStore(),
        content_store=FakeContentStore(),
        agent_file_store=FakeAgentFileStore(),
        resolve_process=ResolveProcess(FakeGitPort()),
        fetch_process=FetchProcess(FakeGitPort()),
        notes_process=NotesProcess(FakeGitPort()),
    )
    with pytest.raises(KeyError):
        cap.execute("spec", RefSpec(RefKind.SEMVER, "^3.0.0"))


def test_upgrade_unsatisfiable_new_spec_raises() -> None:
    """If the new constraint matches no tag, the resolve rule's ValueError propagates.

    The capability mutated the manifest in memory before resolving, but since persistence
    only happens AFTER a successful resolve, the stores are never written on this path.
    """
    git = FakeGitPort()
    git.add_tag(SOURCE, "v2.0.0", "a" * 40)  # only a 2.x tag exists

    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("spec"),
            source=SOURCE,
            spec=RefSpec(RefKind.SEMVER, "^2.0.0"),
        )
    )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile = Lockfile()
    lockfile.put(
        LockEntry(
            name=RefName("spec"),
            ref_type=RefKind.SEMVER,
            resolved="v2.0.0",
            pin=Pin(CommitSha("a" * 40), ContentHash("sha256:" + "2" * 64)),
        )
    )
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)

    cap = UpgradeReference(
        manifest_store=manifest_store,
        lockfile_store=lockfile_store,
        content_store=FakeContentStore(),
        agent_file_store=FakeAgentFileStore(),
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
        notes_process=NotesProcess(git),
    )
    with pytest.raises(ValueError):
        cap.execute("spec", RefSpec(RefKind.SEMVER, "^3.0.0"))  # no 3.x tag
