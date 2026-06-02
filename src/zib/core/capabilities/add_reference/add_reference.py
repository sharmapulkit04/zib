"""add_reference capability (Command) — pin a new external reference into the project.

The user verb: *"I want to add a versioned reference to my project."* This capability
orchestrates the resolve + fetch git interactions, the manifest/lockfile entities, and the
content + agent-file stores. It contains no business logic of its own — it sequences rules,
gateway processes, and ports, and it never calls another capability (CLAUDE.md invariant 1).

State-changer ordering (CLAUDE.md): mutate entities -> persist (manifest / lockfile /
content) -> refresh the agent files LAST. The agent-facing inventory block is rebuilt from
the persisted manifest + lockfile so it always reflects committed state.

A freshly added reference has ``confirmed_through = None``: the agent has not yet asserted
its code conforms to this brand-new reference, so it carries an owed delta (intent §3.2) —
the inventory's ``UPDATE PENDING`` signal fires on first encounter.

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.manifest.manifest import ReferenceEntry
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefName,
    RefSpec,
    Role,
)
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.ports.persistence.stores import (
    AgentFileStore,
    ContentStore,
    LockfileStore,
    ManifestStore,
)
from zib.core.rules.computation.inventory.render_inventory import (
    InventoryItem,
    render_inventory,
)


@dataclass(frozen=True, slots=True)
class AddResult:
    """The outcome of adding a reference — what the shell formats for the user.

    Concrete, value-object-free primitives so the shell prints them directly: the
    reference name, the resolved label it pinned through, the full commit, and the
    canonical content hash that anchors reproducibility.
    """

    name: str
    resolved_label: str
    commit: CommitSha
    content_hash: ContentHash


class AddReference:
    """Resolve, fetch, pin, and materialize a new reference, then refresh the agent block."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        content_store: ContentStore,
        agent_file_store: AgentFileStore,
        resolve_process: ResolveProcess,
        fetch_process: FetchProcess,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._content_store = content_store
        self._agent_file_store = agent_file_store
        self._resolve_process = resolve_process
        self._fetch_process = fetch_process

    def execute(
        self,
        name: str,
        role: str,
        source: str,
        spec: RefSpec,
        subdirectory: str | None = None,
        description: str | None = None,
    ) -> AddResult:
        """Add ``name`` (filling ``role``) from ``source`` at ``spec``.

        Raises:
            ValueError: if a reference with ``name`` is already declared, or if the spec
                resolves to no satisfying tag (propagated from the resolve interaction).
            KeyError: if a BRANCH/REV name is unknown to the source (propagated from the
                git port via the resolve interaction).
        """
        ref_name = RefName(name)

        manifest = self._manifest_store.read()
        if manifest.by_name(ref_name) is not None:
            raise ValueError(f"reference {name!r} already exists")

        # Resolve the spec to a concrete commit + label, then fetch + hash its tree.
        resolved = self._resolve_process.resolve(source, spec)
        fetched = self._fetch_process.fetch(source, resolved.commit, subdirectory)

        pin = Pin(commit=resolved.commit, content_hash=fetched.content_hash)

        # Mutate entities.
        manifest.add(
            ReferenceEntry(
                name=ref_name,
                role=Role(role),
                source=source,
                spec=spec,
                subdirectory=subdirectory,
                description=description,
            )
        )
        lockfile = self._lockfile_store.read()
        lockfile.put(
            LockEntry(
                name=ref_name,
                ref_type=resolved.ref_type,
                resolved=resolved.label,
                pin=pin,
                confirmed_through=None,
            )
        )

        # Persist: manifest, lockfile, content — before touching the agent files.
        self._content_store.materialize(ref_name, resolved.label, fetched.tree)
        self._manifest_store.write(manifest)
        self._lockfile_store.write(lockfile)

        # Refresh the agent-facing inventory block LAST, from committed state.
        self._agent_file_store.write_inventory_block(
            render_inventory(_inventory_items(manifest, lockfile))
        )

        return AddResult(
            name=name,
            resolved_label=resolved.label,
            commit=resolved.commit,
            content_hash=fetched.content_hash,
        )


def _inventory_items(manifest, lockfile) -> list[InventoryItem]:
    """Project the persisted manifest + lockfile into the inventory rendering rows.

    Each declared reference contributes one row; its pinned label, ref type, and owed-delta
    flag come from the matching lock entry. A reference with no lock entry yet (not expected
    on the add path, but kept honest) renders as unpinned with an owed delta.
    """
    items: list[InventoryItem] = []
    for ref in manifest.references:
        lock_entry = lockfile.get(ref.name)
        if lock_entry is None:
            items.append(
                InventoryItem(
                    name=str(ref.name),
                    role=str(ref.role),
                    ref_type=ref.spec.kind.value,
                    resolved="(unpinned)",
                    description=ref.description,
                    owed_delta=True,
                )
            )
            continue
        items.append(
            InventoryItem(
                name=str(ref.name),
                role=str(ref.role),
                ref_type=lock_entry.ref_type.value,
                resolved=lock_entry.resolved,
                description=ref.description,
                owed_delta=lock_entry.has_owed_delta(),
            )
        )
    return items
