"""upgrade_reference capability (Command) — jump a reference to the latest, beyond its
constraint, rewriting the declared intent in the manifest.

This is the one consume verb that edits ``zib.toml`` (solution spec §8 / §8.4). Where
``update`` re-resolves *within* the live constraint and never touches it, ``upgrade`` is
handed a *new* spec by the caller (the CLI/agent computed the bump, e.g. ``^2`` → ``^3``),
**replaces the manifest entry's spec with it first**, then resolves within that new spec and
re-pins to whatever it selects. The constraint change is the point — it's why upgrade is
explicit and user-confirmed at the shell.

Orchestration only (CLAUDE.md — a capability holds no business logic and never calls another
capability). The ordering for a state-changer is fixed:

    1. mutate entities  — swap the manifest entry's spec; resolve; repin the lock entry
    2. persist          — manifest store, then lockfile store, then content store
    3. agent files LAST — refresh the inventory block + ensure the CLAUDE.md import

The load-bearing detail it shares with ``update``: :meth:`LockEntry.repin` **never touches
``confirmed_through``**. After an upgrade the new pin leads the agent's confirmed baseline, so
``has_owed_delta()`` is True and the surfaced :class:`Delta` (computed from that baseline, or
the prior pin when nothing is confirmed yet) is exactly the change the agent still owes.

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import Pin
from zib.core.entities.manifest.manifest import ReferenceEntry
from zib.core.entities.shared.value_objects import CommitSha, RefName, RefSpec
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.notes.translator.notes_types import Delta
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
class UpgradeResult:
    """The outcome of an upgrade — what the shell formats for the user/agent.

    ``old_commit`` is the pin before the upgrade; ``new_commit`` is the freshly resolved pin.
    They are equal only in the degenerate no-op case (the new spec resolves to the same
    commit). ``magnitude`` and ``delta`` are the surfaced "what changed" (solution spec §9):
    the delta is computed from the agent's confirmed baseline when one exists, else from the
    prior pin, so the agent is oriented to the full owed change — never just the last hop.
    """

    name: RefName
    old_commit: CommitSha
    new_commit: CommitSha
    magnitude: str
    delta: Delta


class UpgradeReference:
    """Command capability: bump a reference's constraint and re-pin to the latest it allows."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        content_store: ContentStore,
        agent_file_store: AgentFileStore,
        resolve_process: ResolveProcess,
        fetch_process: FetchProcess,
        notes_process: NotesProcess,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._content_store = content_store
        self._agent_file_store = agent_file_store
        self._resolve = resolve_process
        self._fetch = fetch_process
        self._notes = notes_process

    def execute(self, name: str, new_spec: RefSpec) -> UpgradeResult:
        """Upgrade reference ``name`` to ``new_spec``, surfacing the owed delta.

        Args:
            name: the reference's primary key (the manifest/lockfile/content key).
            new_spec: the rewritten constraint to adopt (e.g. ``^3`` replacing ``^2``).
                Frozen at the constraint level: a ``REV`` ref has nothing newer and a
                ``BRANCH``/``LATEST`` ref is always-newest (use ``update``) — those are
                no-op decisions the shell makes; this capability simply re-resolves and
                re-pins whatever ``new_spec`` selects.

        Raises:
            KeyError: if ``name`` is not declared in the manifest or not present in the
                lockfile (you can only upgrade something already added + pinned).
            ValueError: if ``new_spec`` is satisfied by no available tag (propagated from
                the resolve process / version-resolution rule).

        Returns:
            UpgradeResult with the old and new pins, the magnitude, and the surfaced Delta.
        """
        ref_name = RefName(name)

        manifest = self._manifest_store.read()
        old_entry = manifest.by_name(ref_name)
        if old_entry is None:
            raise KeyError(f"reference {name!r} is not declared in the manifest")

        lockfile = self._lockfile_store.read()
        lock_entry = lockfile.get(ref_name)
        if lock_entry is None:
            raise KeyError(f"reference {name!r} is not pinned in the lockfile")

        # --- 1. mutate entities ------------------------------------------------------
        # Replace the manifest entry's spec FIRST — adopting the new declared intent is the
        # defining act of upgrade. ReferenceEntry is frozen, so we swap it out wholesale,
        # carrying every other field (role, source, subdirectory, description, poll) over.
        upgraded_entry = ReferenceEntry(
            name=old_entry.name,
            role=old_entry.role,
            source=old_entry.source,
            spec=new_spec,
            subdirectory=old_entry.subdirectory,
            description=old_entry.description,
            poll=old_entry.poll,
        )
        manifest.remove(ref_name)
        manifest.add(upgraded_entry)

        # Resolve WITHIN the new spec, against the live tag list.
        resolved = self._resolve.resolve(old_entry.source, new_spec)
        old_commit = lock_entry.pin.commit
        new_commit = resolved.commit

        # The delta range anchors on the agent's conformance baseline when one exists, else
        # the prior pin — so N upgrades/updates without confirm accumulate into one correct
        # widening range (solution spec §9.1/§9.3). Commit-anchored: immutable SHAs only.
        delta_from = (
            lock_entry.confirmed_through.commit
            if lock_entry.confirmed_through is not None
            else old_commit
        )
        delta = self._notes.delta(
            source=old_entry.source,
            from_commit=delta_from,
            to_commit=new_commit,
            subdirectory=old_entry.subdirectory,
            to_tag=_tag_label_for(resolved),
        )

        # Fetch the new tree + its content hash, then re-pin. repin() leaves
        # confirmed_through untouched → the new pin leads the baseline (owed delta).
        fetched = self._fetch.fetch(old_entry.source, new_commit, old_entry.subdirectory)
        lock_entry.repin(
            resolved=resolved.label,
            ref_type=resolved.ref_type,
            pin=Pin(commit=new_commit, content_hash=fetched.content_hash),
        )

        # --- 2. persist (manifest, then lockfile, then content) ----------------------
        self._manifest_store.write(manifest)
        self._lockfile_store.write(lockfile)
        self._content_store.materialize(ref_name, resolved.label, fetched.tree)

        # --- 3. agent files LAST -----------------------------------------------------
        self._agent_file_store.write_inventory_block(_render_block(manifest, lockfile))
        self._agent_file_store.ensure_claude_import()

        return UpgradeResult(
            name=ref_name,
            old_commit=old_commit,
            new_commit=new_commit,
            magnitude=delta.magnitude.value,
            delta=delta,
        )


def _tag_label_for(resolved) -> str | None:
    """The to-side tag name for annotated-release notes — present only for tag-backed pins.

    Branch/rev pins have no producer release tag, so the notes process gets ``None`` and the
    delta degrades to the commit-log surface (solution spec §9.1, branch refs).
    """
    from zib.core.entities.shared.value_objects import RefKind

    if resolved.ref_type in (RefKind.SEMVER, RefKind.LATEST, RefKind.TAG):
        return resolved.label
    return None


def _render_block(manifest, lockfile) -> str:
    """Rebuild the AGENTS.md inventory body from the post-upgrade manifest + lockfile.

    Assembly only — the cascade (description → name·role) and owed-delta signal live in the
    render rule. Each manifest entry is paired with its lock entry by name; the owed-delta
    flag is the lock entry's own ``has_owed_delta()`` (True right after this upgrade).
    """
    items: list[InventoryItem] = []
    for entry in manifest.references:
        locked = lockfile.get(entry.name)
        if locked is None:
            continue
        items.append(
            InventoryItem(
                name=str(entry.name),
                role=str(entry.role),
                ref_type=locked.ref_type.value,
                resolved=locked.resolved,
                description=entry.description,
                owed_delta=locked.has_owed_delta(),
            )
        )
    return render_inventory(items)
