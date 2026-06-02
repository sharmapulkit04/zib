"""Scenario tests for the ``init`` capability.

Real capability + real render_inventory rule, wired to in-memory fake stores (no mocking of
rules). Each scenario asserts concrete post-state through the fakes.
"""

from __future__ import annotations

import pytest

from tests.capabilities.init_scenarios import EMPTY_INVENTORY_BODY, SCENARIOS
from tests.ports.persistence.fakes import FakeAgentFileStore, FakeManifestStore
from zib.core.capabilities.init.init import InitCapability, InitResult
from zib.core.entities.manifest.manifest import Manifest


def _build(preexisting: bool) -> tuple[InitCapability, FakeManifestStore, FakeAgentFileStore]:
    manifest_store = FakeManifestStore()
    agent_file_store = FakeAgentFileStore()
    if preexisting:
        manifest_store.write(Manifest())
    cap = InitCapability(manifest_store, agent_file_store)
    return cap, manifest_store, agent_file_store


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_init_scenarios(key: str) -> None:
    scenario = SCENARIOS[key]
    cap, manifest_store, agent_file_store = _build(scenario["input"]["preexisting"])

    result = cap.execute()
    expect = scenario["expect"]

    assert isinstance(result, InitResult)
    assert result.created is expect["created"]
    assert manifest_store.exists() is expect["manifest_exists"]
    assert len(manifest_store.read().references) == expect["manifest_reference_count"]
    assert agent_file_store.claude_imported is expect["claude_imported"]
    assert agent_file_store.last_block == expect["inventory_block"]


def test_creates_workspace_when_absent() -> None:
    cap, manifest_store, agent_file_store = _build(preexisting=False)

    assert manifest_store.exists() is False

    result = cap.execute()

    assert result.created is True
    assert manifest_store.exists() is True
    assert manifest_store.read().references == []
    assert agent_file_store.claude_imported is True
    assert agent_file_store.last_block == EMPTY_INVENTORY_BODY


def test_idempotent_when_manifest_present() -> None:
    cap, manifest_store, agent_file_store = _build(preexisting=True)

    result = cap.execute()

    assert result.created is False
    # Idempotent no-op: agent files were never touched.
    assert agent_file_store.claude_imported is False
    assert agent_file_store.last_block is None
    assert len(manifest_store.read().references) == 0


def test_does_not_clobber_existing_references() -> None:
    from zib.core.entities.shared.value_objects import RefName, RefSpec, RefKind, Role
    from zib.core.entities.manifest.manifest import ReferenceEntry

    manifest_store = FakeManifestStore()
    agent_file_store = FakeAgentFileStore()
    existing = Manifest()
    existing.add(
        ReferenceEntry(
            name=RefName("spec"),
            role=Role("api-spec"),
            source="acme/spec",
            spec=RefSpec(RefKind.LATEST, None),
        )
    )
    manifest_store.write(existing)

    result = InitCapability(manifest_store, agent_file_store).execute()

    assert result.created is False
    # The existing reference survives untouched — init never overwrites a real workspace.
    assert len(manifest_store.read().references) == 1
    assert str(manifest_store.read().references[0].name) == "spec"
    assert agent_file_store.last_block is None


def test_result_is_immutable() -> None:
    result = InitResult(created=True)
    with pytest.raises(Exception):
        result.created = False  # type: ignore[misc]
