"""Scenario tests for the outdated capability.

Real rule (``assess_drift``) + real aggregates wired to FakeGitPort and the fake
persistence stores (no mocking of rules — CLAUDE.md). Each scenario seeds one declared
reference, its lock entry, and the live tag list, runs the read-only poll, and asserts the
exact ``drift_status`` / ``target`` / ``owed_delta`` reported. Extra cases cover the branch
(tracking-tip) and rev (frozen) lanes plus multi-ref aggregation and read-only-ness.
"""

from __future__ import annotations

import pytest

from tests.capabilities.outdated_scenarios import (
    LATEST_COMMIT,
    PIN_COMMIT,
    PIN_HASH,
    SOURCE,
    SCENARIOS,
)
from tests.gateways.git.port.fake_git_port import FakeGitPort
from tests.ports.persistence.fakes import FakeLockfileStore, FakeManifestStore
from zib.core.capabilities.outdated.outdated import Outdated, OutdatedItem
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

_PRIOR_COMMIT = "d" * 40
_PRIOR_HASH = "sha256:" + ("d" * 64)


def _ref_type(name: str) -> RefKind:
    return RefKind(name)


def _build_one(name, *, spec, ref_type, resolved, confirmed, tags=(), branch=None):
    """Seed a single-reference manifest + lockfile and a configured FakeGitPort."""
    ref = RefName(name)
    refspec = RefSpec.from_manifest(**spec)

    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=ref,
            role=Role(f"role-{name}"),
            source=SOURCE,
            spec=refspec,
        )
    )

    pin = Pin(CommitSha(PIN_COMMIT), ContentHash(PIN_HASH))
    confirmed_through = pin if confirmed else Pin(
        CommitSha(_PRIOR_COMMIT), ContentHash(_PRIOR_HASH)
    )
    lockfile = Lockfile()
    lockfile.put(
        LockEntry(
            name=ref,
            ref_type=_ref_type(ref_type),
            resolved=resolved,
            pin=pin,
            confirmed_through=confirmed_through,
        )
    )

    git = FakeGitPort()
    for tag_name, commit_hex in tags:
        git.add_tag(SOURCE, tag_name, commit_hex)
    if branch is not None:
        git.set_branch(SOURCE, branch, branch_tip_for(branch))

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)
    return Outdated(manifest_store, lockfile_store, git), git, lockfile_store


# branch tip overrides per test (filled in by branch tests directly)
_BRANCH_TIPS: dict[str, str] = {}


def branch_tip_for(branch: str) -> str:
    return _BRANCH_TIPS.get(branch, PIN_COMMIT)


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_outdated_scenarios(key):
    scenario = SCENARIOS[key]
    inp = scenario["input"]
    expect = scenario["expect"]

    cap, _git, _lock = _build_one(
        "spec",
        spec=inp["spec"],
        ref_type=inp["ref_type"],
        resolved=inp["resolved"],
        confirmed=inp["confirmed"],
        tags=inp["tags"],
    )

    items = cap.execute()

    assert len(items) == 1
    item = items[0]
    assert isinstance(item, OutdatedItem)
    assert item.name == "spec"
    assert item.drift_status == expect["drift_status"]
    assert item.target == expect["target"]
    assert item.owed_delta is expect["owed_delta"]


def test_branch_tip_moved_is_update_available():
    """A branch ref whose tip has moved past the pin reports update_available, no target."""
    _BRANCH_TIPS["main"] = LATEST_COMMIT  # tip differs from PIN_COMMIT
    cap, _git, _lock = _build_one(
        "spec",
        spec={"branch": "main"},
        ref_type="branch",
        resolved="main",
        confirmed=True,
        branch="main",
    )

    item = cap.execute()[0]

    assert item.drift_status == "update_available"
    assert item.target is None
    assert item.owed_delta is False
    _BRANCH_TIPS.clear()


def test_branch_tip_unchanged_is_up_to_date():
    """A branch ref whose tip equals the pin reports up_to_date."""
    _BRANCH_TIPS["main"] = PIN_COMMIT  # tip == pin
    cap, _git, _lock = _build_one(
        "spec",
        spec={"branch": "main"},
        ref_type="branch",
        resolved="main",
        confirmed=True,
        branch="main",
    )

    item = cap.execute()[0]

    assert item.drift_status == "up_to_date"
    assert item.target is None
    assert item.owed_delta is False
    _BRANCH_TIPS.clear()


def test_rev_pinned_is_always_up_to_date():
    """A frozen rev never moves: up_to_date with no target, even with newer tags around."""
    cap, _git, _lock = _build_one(
        "spec",
        spec={"rev": PIN_COMMIT},
        ref_type="rev",
        resolved=CommitSha(PIN_COMMIT).short(),
        confirmed=True,
        tags=[("9.9.9", LATEST_COMMIT)],  # would-be-newer tags are irrelevant for a rev
    )

    item = cap.execute()[0]

    assert item.drift_status == "up_to_date"
    assert item.target is None
    assert item.owed_delta is False


def test_branch_owed_delta_surfaces_alongside_up_to_date_tip():
    """Owed delta is independent of drift: a branch with an unchanged tip can still owe."""
    _BRANCH_TIPS["main"] = PIN_COMMIT
    cap, _git, _lock = _build_one(
        "spec",
        spec={"branch": "main"},
        ref_type="branch",
        resolved="main",
        confirmed=False,  # confirmed baseline behind the pin
        branch="main",
    )

    item = cap.execute()[0]

    assert item.drift_status == "up_to_date"
    assert item.owed_delta is True
    _BRANCH_TIPS.clear()


def test_polls_all_references_and_mutates_nothing():
    """Aggregates over every declared ref; the poll is strictly read-only."""
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("primary"),
            source=SOURCE,
            spec=RefSpec.from_manifest(version="^2.1.0"),
        )
    )
    manifest.add(
        ReferenceEntry(
            name=RefName("style"),
            role=Role("style"),
            source="acme/style",
            spec=RefSpec.from_manifest(rev=PIN_COMMIT),
        )
    )

    spec_pin = Pin(CommitSha(PIN_COMMIT), ContentHash(PIN_HASH))
    style_pin = Pin(CommitSha("e" * 40), ContentHash("sha256:" + "e" * 64))
    lockfile = Lockfile()
    lockfile.put(
        LockEntry(
            name=RefName("spec"),
            ref_type=RefKind.SEMVER,
            resolved="2.1.0",
            pin=spec_pin,
            confirmed_through=spec_pin,
        )
    )
    lockfile.put(
        LockEntry(
            name=RefName("style"),
            ref_type=RefKind.REV,
            resolved=CommitSha("e" * 40).short(),
            pin=style_pin,
            confirmed_through=style_pin,
        )
    )

    git = FakeGitPort()
    git.add_tag(SOURCE, "2.1.0", PIN_COMMIT)
    git.add_tag(SOURCE, "2.1.5", LATEST_COMMIT)

    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()
    lockfile_store.write(lockfile)

    # Capture state before to prove read-only-ness.
    before_lock_len = len(lockfile_store.read())

    items = Outdated(manifest_store, lockfile_store, git).execute()

    by_name = {item.name: item for item in items}
    assert len(items) == 2
    assert by_name["spec"].drift_status == "update_available"
    assert by_name["spec"].target == "2.1.5"
    assert by_name["style"].drift_status == "up_to_date"
    assert by_name["style"].target is None

    # Read-only: lockfile unchanged, pins untouched.
    assert len(lockfile_store.read()) == before_lock_len
    assert lockfile_store.read().get(RefName("spec")).pin.commit == CommitSha(PIN_COMMIT)


def test_declared_but_not_locked_reference_is_skipped():
    """A reference declared in the manifest but absent from the lockfile is not polled."""
    manifest = Manifest()
    manifest.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("primary"),
            source=SOURCE,
            spec=RefSpec.from_manifest(version="^2.1.0"),
        )
    )
    manifest_store = FakeManifestStore()
    manifest_store.write(manifest)
    lockfile_store = FakeLockfileStore()  # empty lockfile
    git = FakeGitPort()

    items = Outdated(manifest_store, lockfile_store, git).execute()

    assert items == []


def test_empty_project_reports_nothing():
    manifest_store = FakeManifestStore()
    manifest_store.write(Manifest())
    lockfile_store = FakeLockfileStore()
    items = Outdated(manifest_store, lockfile_store, FakeGitPort()).execute()
    assert items == []
