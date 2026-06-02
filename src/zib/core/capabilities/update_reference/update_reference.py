"""update_reference capability — re-resolve in-range, re-pin, surface the delta.

This is the centerpiece of zib's correctness story (solution spec §15.4/§15.5,
intent §3.2). ``update`` re-resolves a reference *within its existing manifest
constraint* (the SEMVER range / LATEST / TAG / BRANCH it already declared — the
constraint is **never** rewritten here; that is ``upgrade``'s job), moves the pin
to the newly resolved commit, and leaves ``confirmed_through`` exactly where it was.

That untouched baseline is the load-bearing detail: after a successful update the
pin *leads* the confirmed baseline, and that lead **is** the delta the agent still
owes (``LockEntry.has_owed_delta()`` → True). Nothing is silently absorbed — N
updates without a ``confirm`` accumulate one correct widening range. zib computes
and surfaces *what changed*; the agent applies it and asserts conformance via
``confirm``.

Orchestration only — no business logic here (CLAUDE.md: capabilities orchestrate
rules / ports / gateway processes and never call another capability). The ordering
for this state-changer is fixed: mutate the entity → persist (lock + content) →
refresh the agent-facing inventory block LAST.

State-changing flow:

    load manifest + lock
    ref   = manifest.by_name(name)         (must be declared)
    entry = lock.get(name)                 (must be pinned)
    resolved = resolve_process.resolve(source, ref.spec)   # within the EXISTING spec
    if resolved.commit == entry.pin.commit:
        → up_to_date, no mutation, return
    else:
        delta   = notes_process.delta(from=entry.pin.commit, to=resolved.commit, ...)
        fetched = fetch_process.fetch(source, resolved.commit, subdirectory)
        entry.repin(resolved=label, ref_type=resolved.ref_type, pin=(commit, hash))
                                              # confirmed_through stays untouched
        content_store.materialize(...)
        lockfile_store.write(lock)
        agent_file_store.write_inventory_block(render_inventory(...))   # LAST

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import Pin
from zib.core.entities.shared.value_objects import RefName
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
from zib.core.rules.computation.delta.delta import Magnitude
from zib.core.rules.computation.inventory.render_inventory import (
    InventoryItem,
    render_inventory,
)

# Ref kinds whose resolution label is a literal tag name — only then does a tag
# message ("release notes") exist to surface alongside the diff.
_TAG_BACKED_LABELS = frozenset({"semver", "latest", "tag"})


@dataclass(frozen=True, slots=True)
class UpdateResult:
    """The outcome of an ``update`` for one reference.

    ``up_to_date`` is True when re-resolution landed on the already-pinned commit
    (no mutation happened, ``old_commit == new_commit``, ``magnitude``/``delta`` are
    ``None``). Otherwise the pin moved: ``old_commit``/``new_commit`` are the short
    SHAs, ``magnitude`` is the churn verdict, and ``delta`` is the full surfaced
    change the agent reads.
    """

    name: str
    up_to_date: bool
    old_commit: str
    new_commit: str
    magnitude: Magnitude | None
    delta: Delta | None


class UpdateReference:
    """Re-resolve a reference within its constraint, re-pin, and surface the delta."""

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

    def execute(self, name: str) -> UpdateResult:
        """Update the reference named ``name`` within its existing manifest constraint.

        Raises:
            ValueError: when ``name`` is not declared in the manifest or not pinned in
                the lockfile (an update has nothing to act on).
            ValueError: when re-resolution finds no satisfying tag (propagated from the
                resolve process / version-resolution rule).
        """
        ref_name = RefName(name)

        manifest = self._manifest_store.read()
        lockfile = self._lockfile_store.read()

        ref = manifest.by_name(ref_name)
        if ref is None:
            raise ValueError(f"reference {name!r} is not declared in the manifest")

        entry = lockfile.get(ref_name)
        if entry is None:
            raise ValueError(f"reference {name!r} is not pinned in the lockfile")

        old_commit = entry.pin.commit
        resolved = self._resolve.resolve(ref.source, ref.spec)

        # No movement — re-resolution landed on the already-pinned commit. The tool
        # is deterministic: nothing changes, nothing is rewritten, no delta is owed.
        if resolved.commit == old_commit:
            short = old_commit.short()
            return UpdateResult(
                name=name,
                up_to_date=True,
                old_commit=short,
                new_commit=short,
                magnitude=None,
                delta=None,
            )

        # The pin moved. Surface what changed across the SHA-immutable range, then
        # fetch the new tree so the pin's content hash reproduces the exact bytes.
        to_tag = (
            resolved.label
            if resolved.ref_type.value in _TAG_BACKED_LABELS
            else None
        )
        delta = self._notes.delta(
            ref.source,
            old_commit,
            resolved.commit,
            ref.subdirectory,
            to_tag=to_tag,
        )
        fetched = self._fetch.fetch(ref.source, resolved.commit, ref.subdirectory)

        # Mutate the entity. repin() deliberately leaves confirmed_through alone, so the
        # new pin leads the confirmed baseline — that lead is the owed delta.
        entry.repin(
            resolved=resolved.label,
            ref_type=resolved.ref_type,
            pin=Pin(resolved.commit, fetched.content_hash),
        )

        # Persist: content first, then the lockfile that points at it.
        self._content_store.materialize(ref_name, resolved.label, fetched.tree)
        self._lockfile_store.write(lockfile)

        # Agent-facing files LAST — refresh the whole inventory block so the moved
        # reference now renders its UPDATE PENDING line.
        self._agent_file_store.write_inventory_block(
            render_inventory(self._build_inventory(manifest, lockfile))
        )

        return UpdateResult(
            name=name,
            up_to_date=False,
            old_commit=old_commit.short(),
            new_commit=resolved.commit.short(),
            magnitude=delta.magnitude,
            delta=delta,
        )

    def _build_inventory(self, manifest, lockfile) -> list[InventoryItem]:
        """Project the current manifest + lock into the agent-facing inventory items.

        Pairs each pinned lock entry with its manifest declaration (role/description),
        carrying the owed-delta flag the agent reads to know a change is pending.
        """
        items: list[InventoryItem] = []
        for lock_entry in lockfile:
            ref = manifest.by_name(lock_entry.name)
            if ref is None:
                continue
            items.append(
                InventoryItem(
                    name=str(lock_entry.name),
                    role=str(ref.role),
                    ref_type=lock_entry.ref_type.value,
                    resolved=lock_entry.resolved,
                    description=ref.description,
                    owed_delta=lock_entry.has_owed_delta(),
                )
            )
        return items
