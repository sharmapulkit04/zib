"""read_reference capability (Query) — what the agent actually reads (``zib cat``).

This is the *select-and-read* surface from the agent workflow (solution spec §10:
"find the relevant spec from the inventory ... then ``zib cat <name>`` **only the
chosen** reference"). After the agent has picked a reference by ``name`` / ``role``
from the inventory, this hands back the materialized content of the *pinned*
reference — the exact committed bytes that reproduce its ``content_hash`` — so the
agent reads the right reference at the right version.

Query capability: orchestration only, no business logic (CLAUDE.md — capabilities
orchestrate ports/rules; they never decide). It pairs the manifest (declared intent:
is this reference even ours?) with the lockfile (pinned reality: what commit/label is
fetched?), then reads the on-disk tree from the content store keyed by the lock entry's
``resolved`` label. It mutates nothing and persists nothing — a pure read, re-runnable.

Why the lockfile's ``resolved`` and not the manifest's spec: the manifest spec may be a
*range* (``^2.1.0``) or ``latest`` — it does not name a concrete on-disk label. The
content store is keyed by the resolved label the pin actually fetched (a tag / branch /
short sha), so the read must go through the lock entry, never the declared spec.

Three ways a read is unavailable, each a distinct ValueError so the shell can guide the
agent precisely:
  * the name isn't declared in the manifest      → it's not a zib reference at all
  * it's declared but not yet pinned (no lock)    → run ``zib install`` first
  * it's pinned but content isn't materialized     → run ``zib install`` to fetch it
A malformed name raises at the value-object boundary before any lookup.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest
from zib.core.entities.shared.value_objects import RefName, TreeEntry
from zib.core.ports.persistence.stores import (
    ContentStore,
    LockfileStore,
    ManifestStore,
)


class ReadReference:
    """Return the materialized tree of one pinned reference for the agent to read."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        content_store: ContentStore,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._content_store = content_store

    def execute(self, name: str) -> list[TreeEntry]:
        """Read the pinned content of reference ``name`` from the content store.

        ``name`` is the developer/agent-supplied handle; constructing :class:`RefName`
        validates it at the boundary (raises ``ValueError`` for a malformed name).

        Raises ``ValueError`` when the reference is not declared, not yet pinned, or its
        content has not been materialized — each with a distinct, actionable message.
        Returns the list of :class:`TreeEntry` exactly as stored (the bytes that hash to
        the pin's ``content_hash``). Pure read: nothing is written to any store.
        """
        ref = RefName(name)

        manifest: Manifest = self._manifest_store.read()
        if manifest.by_name(ref) is None:
            raise ValueError(f"reference {ref} is not declared")

        lockfile: Lockfile = self._lockfile_store.read()
        lock_entry = lockfile.get(ref)
        if lock_entry is None:
            raise ValueError(
                f"reference {ref} is declared but not pinned; run `zib install`"
            )

        try:
            return self._content_store.read_tree(ref, lock_entry.resolved)
        except KeyError as missing:
            raise ValueError(
                f"reference {ref} is pinned at {lock_entry.resolved!r} but its content "
                f"is not materialized; run `zib install`"
            ) from missing
