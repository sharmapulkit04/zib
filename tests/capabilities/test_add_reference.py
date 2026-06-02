"""Scenario tests for the add_reference capability.

Real rules + real gateway processes (ResolveProcess / FetchProcess) wired to the validated
FakeGitPort and the in-memory fake stores — no mocking of rules (CLAUDE.md: the scenario test
IS the capability's test). Assertions are concrete: exact labels, commits, counts, the
owed-delta flag, content verification, and the agent block contents.
"""

from __future__ import annotations

import pytest

from tests.capabilities.add_reference_scenarios import SCENARIOS
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import (
    FakeAgentFileStore,
    FakeContentStore,
    FakeLockfileStore,
    FakeManifestStore,
)
from zib.core.capabilities.add_reference.add_reference import (
    AddReference,
    AddResult,
)
from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.manifest.manifest import ReferenceEntry
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefName,
    RefSpec,
    Role,
    TreeEntry,
)
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash


def _spec(case_input) -> RefSpec:
    kind = case_input["ref_kind"]
    return RefSpec.from_manifest(**{kind: case_input["ref_value"]})


def _build(fixtures) -> tuple[AddReference, FakeGitPort, dict]:
    git = FakeGitPort()
    for name, commit in fixtures["tags"]:
        git.add_tag(SCENARIOS_SOURCE, name, commit)
    for name, commit in fixtures["branches"]:
        git.set_branch(SCENARIOS_SOURCE, name, commit)
    for commit, entries in fixtures["trees"].items():
        git.set_tree(
            SCENARIOS_SOURCE,
            commit,
            [TreeEntry(path, mode, blob) for path, mode, blob in entries],
        )

    stores = {
        "manifest": FakeManifestStore(),
        "lockfile": FakeLockfileStore(),
        "content": FakeContentStore(),
        "agent": FakeAgentFileStore(),
    }
    cap = AddReference(
        manifest_store=stores["manifest"],
        lockfile_store=stores["lockfile"],
        content_store=stores["content"],
        agent_file_store=stores["agent"],
        resolve_process=ResolveProcess(git),
        fetch_process=FetchProcess(git),
    )
    return cap, git, stores


SCENARIOS_SOURCE = "acme/spec"


def _seed_preexisting(stores, pre) -> None:
    """Put an existing reference into both stores so the duplicate-name path triggers."""
    manifest = stores["manifest"].read()
    name = RefName(pre["name"])
    manifest.add(
        ReferenceEntry(
            name=name,
            role=Role(pre["role"]),
            source=pre["source"],
            spec=RefSpec.from_manifest(**{pre["ref_kind"]: pre["ref_value"]}),
        )
    )
    stores["manifest"].write(manifest)
    lockfile = stores["lockfile"].read()
    lockfile.put(
        LockEntry(
            name=name,
            ref_type=manifest.by_name(name).spec.kind,
            resolved="2.1.0",
            pin=Pin(CommitSha("a" * 40), ContentHash("sha256:" + "0" * 64)),
        )
    )
    stores["lockfile"].write(lockfile)


@pytest.mark.parametrize(
    "key", ["add_semver_picks_highest_in_range", "add_branch_pins_tip"]
)
def test_add_reference_happy_paths(key) -> None:
    scenario = SCENARIOS[key]
    case_input = scenario["input"]
    expect = scenario["expect"]
    cap, _git, stores = _build(scenario["fixtures"])

    result = cap.execute(
        name=case_input["name"],
        role=case_input["role"],
        source=case_input["source"],
        spec=_spec(case_input),
        subdirectory=case_input["subdirectory"],
        description=case_input["description"],
    )

    # Result carries concrete pinned coordinates.
    assert isinstance(result, AddResult)
    assert result.name == case_input["name"]
    assert result.resolved_label == expect["resolved_label"]
    assert result.commit == CommitSha(expect["commit"])

    # Manifest persisted with exactly the new reference.
    manifest = stores["manifest"].read()
    assert len(manifest.references) == expect["manifest_count"]
    ref = manifest.by_name(RefName(case_input["name"]))
    assert ref is not None
    assert str(ref.role) == case_input["role"]
    assert ref.source == case_input["source"]

    # Lockfile persisted: right type, label, and fresh add => owed delta.
    lockfile = stores["lockfile"].read()
    assert len(lockfile) == expect["lock_count"]
    entry = lockfile.get(RefName(case_input["name"]))
    assert entry is not None
    assert entry.ref_type.value == expect["ref_type"]
    assert entry.resolved == expect["resolved_label"]
    assert entry.pin.commit == CommitSha(expect["commit"])
    assert entry.confirmed_through is None
    assert entry.has_owed_delta() is expect["owed_delta"]

    # Content materialized under (name, label) and verifies against the pin's hash.
    assert (
        stores["content"].verify(
            RefName(case_input["name"]), expect["resolved_label"], entry.pin.content_hash
        )
        is expect["content_verifies"]
    )

    # Agent block refreshed last; CLAUDE.md import untouched by add.
    assert stores["agent"].claude_imported is expect["claude_imported"]
    body = stores["agent"].last_block
    assert body is not None
    assert expect["block_contains"] in body
    assert ("UPDATE PENDING" in body) is expect["block_contains_pending"]


def test_add_duplicate_name_errors() -> None:
    scenario = SCENARIOS["add_duplicate_name_errors"]
    case_input = scenario["input"]
    cap, _git, stores = _build(scenario["fixtures"])
    _seed_preexisting(stores, scenario["preexisting"])

    with pytest.raises(ValueError, match=scenario["expect"]["error"]):
        cap.execute(
            name=case_input["name"],
            role=case_input["role"],
            source=case_input["source"],
            spec=_spec(case_input),
            subdirectory=case_input["subdirectory"],
            description=case_input["description"],
        )

    # Nothing new added: still exactly the one pre-existing reference, untouched.
    assert len(stores["manifest"].read().references) == 1
    assert len(stores["lockfile"].read()) == 1


def test_content_hash_matches_fetched_tree() -> None:
    """The pin's content hash equals the canonical hash over the materialized tree."""
    scenario = SCENARIOS["add_semver_picks_highest_in_range"]
    case_input = scenario["input"]
    cap, _git, stores = _build(scenario["fixtures"])

    result = cap.execute(
        name=case_input["name"],
        role=case_input["role"],
        source=case_input["source"],
        spec=_spec(case_input),
    )

    stored_tree = stores["content"].read_tree(
        RefName(case_input["name"]), result.resolved_label
    )
    assert compute_content_hash(stored_tree) == result.content_hash
    assert result.content_hash == ContentHash(result.content_hash.value)


def test_branch_ref_type_and_label() -> None:
    """A branch ref pins the tip, labels by branch name, and types as BRANCH."""
    scenario = SCENARIOS["add_branch_pins_tip"]
    case_input = scenario["input"]
    cap, _git, stores = _build(scenario["fixtures"])

    result = cap.execute(
        name=case_input["name"],
        role=case_input["role"],
        source=case_input["source"],
        spec=_spec(case_input),
    )

    assert result.resolved_label == "main"
    assert result.commit == CommitSha("d" * 40)
    entry = stores["lockfile"].read().get(RefName(case_input["name"]))
    assert entry.ref_type.value == "branch"
