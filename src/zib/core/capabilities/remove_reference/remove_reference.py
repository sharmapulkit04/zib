"""remove_reference capability (Command) — drop a reference entirely.

``zib remove <name>`` removes the reference from all three places it lives
(solution spec §6, command table, §15): the manifest (declared intent), the
lockfile (pinned reality), and the materialized content under
``.zib/references/<name>/``. Removal is *recoverable* only via git history — zib
keeps no ``.trash/`` (spec "recoverable removal", §10).

Orchestration only — no business logic here (CLAUDE.md: capabilities orchestrate
rules/ports; they never decide). The one rule it leans on is ``render_inventory``,
used to rebuild zib's managed ``AGENTS.md`` block from the *surviving* references so
the agent's inventory no longer lists what was removed (spec §11 — every
reference-set change refreshes the block interior).

State-changer ordering is fixed (CLAUDE.md): mutate the aggregates, persist them
(manifest → lockfile → content), then update the agent files LAST. The agent file
is touched only after the durable stores agree, so a half-written block can never
advertise a state the lockfile doesn't back.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import RefName
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
class RemoveResult:
    """What ``remove`` reports back: the name of the reference that was removed.

    Frozen — a capability result is a value the shell formats, never mutates.
    """

    name: str


class RemoveReference:
    """Remove a reference from manifest + lockfile + content, then refresh the block."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        content_store: ContentStore,
        agent_file_store: AgentFileStore,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._content_store = content_store
        self._agent_file_store = agent_file_store

    def execute(self, name: str) -> RemoveResult:
        """Remove ``name`` everywhere it lives. Raises if it isn't declared.

        ``name`` arriving as a raw string is validated into a :class:`RefName` at the
        boundary (an invalid name can't match a declared reference anyway). Missing
        references are a clear, named error — there is nothing to remove.
        """
        ref_name = RefName(name)

        manifest = self._manifest_store.read()
        if manifest.by_name(ref_name) is None:
            raise ValueError(f"reference {name!r} is not declared; nothing to remove")

        # 1. mutate entities — drop from both aggregates (independent lifecycles)
        manifest.remove(ref_name)
        lockfile = self._lockfile_store.read()
        lockfile.remove(ref_name)

        # 2. persist — manifest, lockfile, then delete the materialized content tree
        self._manifest_store.write(manifest)
        self._lockfile_store.write(lockfile)
        self._content_store.remove(ref_name)

        # 3. agent files LAST — rebuild the inventory block from the survivors
        self._agent_file_store.write_inventory_block(
            render_inventory(self._surviving_items(manifest, lockfile))
        )

        return RemoveResult(name=name)

    @staticmethod
    def _surviving_items(manifest, lockfile) -> list[InventoryItem]:
        """Project the references that remain into inventory items for the block.

        Pairs each surviving manifest entry with its lock entry (if pinned) so the
        rendered block carries the pinned label/type and the owed-delta flag. A
        declared-but-not-yet-installed reference still appears, marked as pending.
        """
        items: list[InventoryItem] = []
        for entry in manifest.references:
            lock_entry = lockfile.get(entry.name)
            if lock_entry is not None:
                ref_type = lock_entry.ref_type.value
                resolved = lock_entry.resolved
                owed_delta = lock_entry.has_owed_delta()
            else:
                ref_type = entry.spec.kind.value
                resolved = "not installed"
                owed_delta = False
            items.append(
                InventoryItem(
                    name=str(entry.name),
                    role=str(entry.role),
                    ref_type=ref_type,
                    resolved=resolved,
                    description=entry.description,
                    owed_delta=owed_delta,
                )
            )
        return items
