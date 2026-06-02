"""swap_reference capability — replace the reference filling a role (Command).

The user wants to switch the *reference filling a need* to a better alternative, in one
clean move rather than a fragile remove-then-re-add (intent §3.3, solution spec §8.2).

Swap is keyed on the **role**: it finds the single reference currently filling that role,
removes it (manifest + lockfile + on-disk content — recoverable via git history), and adds
the new reference *under the same role*. Resolution + fetch + pin run exactly as for a fresh
add. Crucially the new lock entry has ``confirmed_through = None`` — the conformance baseline
**resets on swap** (a different reference means different usage; the old notes/baseline do not
carry over). That reset is what makes ``has_owed_delta()`` True for the freshly-swapped-in
reference, so the agent is told to read and apply it (intent §3.4, §3.6).

Orchestration only — no business logic lives here (CLAUDE.md). Ordering for a state-changer:

    mutate entities (manifest, lockfile)
      -> persist (manifest_store, lockfile_store, content_store)
      -> update agent files (agent_file_store) LAST

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.entities.shared.value_objects import RefName, RefSpec, Role
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
class SwapResult:
    """The outcome of a swap — which role was affected and what moved in/out.

    Attributes:
        role: the role whose filling reference was replaced (preserved across the swap).
        removed_name: the name of the reference that was swapped out (now recoverable only
            via git history).
        added_name: the name of the reference now filling the role, freshly pinned with a
            reset conformance baseline (it has an owed delta until the agent confirms).
    """

    role: str
    removed_name: str
    added_name: str


class SwapReference:
    """Replace the single reference filling a role with a new one under the same role."""

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
        self._resolve = resolve_process
        self._fetch = fetch_process

    def execute(
        self,
        role: str,
        new_name: str,
        new_source: str,
        new_spec: RefSpec,
        subdirectory: str | None = None,
        description: str | None = None,
    ) -> SwapResult:
        """Swap the reference filling ``role`` for a new one under the same role.

        Raises:
            ValueError: when ``role`` is filled by zero references (nothing to swap) or by
                more than one (ambiguous — the caller must use a name-keyed move instead).
                Also propagates any value-object construction error.
            ValueError / KeyError: from resolution/fetch when the new source/spec cannot be
                resolved (propagated unchanged from the git gateway processes).
        """
        role_vo = Role(role)
        new_name_vo = RefName(new_name)

        manifest = self._manifest_store.read()
        lockfile = self._lockfile_store.read()

        filling = manifest.by_role(role_vo)
        if len(filling) == 0:
            raise ValueError(f"no reference fills role {role!r}; nothing to swap")
        if len(filling) > 1:
            raise ValueError(
                f"role {role!r} is filled by {len(filling)} references "
                f"({', '.join(str(r.name) for r in filling)}); "
                "swap is ambiguous — remove the specific one and add the replacement"
            )

        old = filling[0]
        old_name = old.name

        # --- resolve + fetch the NEW reference (read-only git interactions) ---
        resolved = self._resolve.resolve(new_source, new_spec)
        fetched = self._fetch.fetch(new_source, resolved.commit, subdirectory)

        # --- mutate entities: remove the old, add the new under the SAME role ---
        manifest.remove(old_name)
        manifest.add(
            ReferenceEntry(
                name=new_name_vo,
                role=role_vo,
                source=new_source,
                spec=new_spec,
                subdirectory=subdirectory,
                description=description,
            )
        )

        lockfile.remove(old_name)
        lockfile.put(
            LockEntry(
                name=new_name_vo,
                ref_type=resolved.ref_type,
                resolved=resolved.label,
                pin=Pin(commit=resolved.commit, content_hash=fetched.content_hash),
                confirmed_through=None,  # baseline RESETS on swap (intent §3.3/§3.4)
            )
        )

        # --- persist: manifest, lockfile, content ---
        self._manifest_store.write(manifest)
        self._lockfile_store.write(lockfile)
        self._content_store.remove(old_name)
        self._content_store.materialize(new_name_vo, resolved.label, fetched.tree)

        # --- update agent files LAST ---
        self._agent_file_store.write_inventory_block(
            _render_block(manifest, lockfile)
        )

        return SwapResult(
            role=role,
            removed_name=str(old_name),
            added_name=new_name,
        )


def _render_block(manifest: Manifest, lockfile: Lockfile) -> str:
    """Build the AGENTS.md inventory body from the persisted manifest + lockfile state.

    Pairs each declared reference with its lock entry (by name) to surface the pinned
    label, ref type, and whether a delta is owed. References not yet locked are skipped —
    the inventory reflects installed reality.
    """
    items: list[InventoryItem] = []
    for entry in manifest.references:
        lock = lockfile.get(entry.name)
        if lock is None:
            continue
        items.append(
            InventoryItem(
                name=str(entry.name),
                role=str(entry.role),
                ref_type=lock.ref_type.value,
                resolved=lock.resolved,
                description=entry.description,
                owed_delta=lock.has_owed_delta(),
            )
        )
    return render_inventory(items)
