"""list_references capability (Query) — the project's reference inventory.

``zib list`` answers "what references does this project pin, and what state is
each in?" (solution spec §6 command table, §4 ``list`` output). It is the
selection surface the agent reads to pick the right spec for a task: each row
carries the reference's ``name``, the ``role`` (slot) it fills, the declared
``ref_type``, its ``resolved`` label, and whether the pin leads the agent's
confirmed baseline — the **owed delta** flag the agent acts on.

Query capability: orchestration only, no business logic (CLAUDE.md — capabilities
orchestrate ports/rules; they never decide). It reads the manifest (declared
intent) and the lockfile (pinned reality), pairs each declared reference with its
lock entry, and projects a flat, name-sorted list of result rows. It mutates
nothing and persists nothing.

The manifest is the source of the *set* of references (a reference is declared
there even before it is installed). The lockfile supplies the pinned state for
each one. A declared-but-not-yet-installed reference still appears — surfaced with
its declared kind and a "not installed" label, never silently dropped — so the
inventory always mirrors the manifest.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest
from zib.core.ports.persistence.stores import LockfileStore, ManifestStore


@dataclass(frozen=True, slots=True)
class RefSummary:
    """One inventory row the shell formats for ``zib list``.

    Frozen — a capability result is a value the shell renders, never mutates.

      * ``name``       — the reference's primary key / display handle.
      * ``role``       — the slot it fills (selection aid; ``--by-role`` groups on it).
      * ``ref_type``   — how it is tracked: ``semver`` / ``tag`` / ``latest`` /
                         ``branch`` / ``rev``. Pinned refs report the lock entry's
                         kind; not-yet-installed refs report the declared kind.
      * ``resolved``   — the resolved label (tag / branch / short sha) when pinned,
                         else ``"not installed"``.
      * ``owed_delta`` — True when the pin leads the confirmed baseline (the agent
                         owes a change). Always False for a not-yet-installed ref —
                         there is no pin to lead anything.
    """

    name: str
    role: str
    ref_type: str
    resolved: str
    owed_delta: bool


_NOT_INSTALLED = "not installed"


class ListReferences:
    """List every declared reference with its current pinned state, sorted by name."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store

    def execute(self) -> list[RefSummary]:
        """Return one :class:`RefSummary` per declared reference, sorted by name.

        Empty manifest → ``[]``. Pure read: nothing is written to either store.
        """
        manifest: Manifest = self._manifest_store.read()
        lockfile: Lockfile = self._lockfile_store.read()

        summaries = [
            self._summarize(entry, lockfile) for entry in manifest.references
        ]
        summaries.sort(key=lambda summary: summary.name)
        return summaries

    @staticmethod
    def _summarize(entry, lockfile: Lockfile) -> RefSummary:
        """Pair a declared reference with its lock entry (if pinned) into a row."""
        lock_entry = lockfile.get(entry.name)
        if lock_entry is not None:
            return RefSummary(
                name=str(entry.name),
                role=str(entry.role),
                ref_type=lock_entry.ref_type.value,
                resolved=lock_entry.resolved,
                owed_delta=lock_entry.has_owed_delta(),
            )
        return RefSummary(
            name=str(entry.name),
            role=str(entry.role),
            ref_type=entry.spec.kind.value,
            resolved=_NOT_INSTALLED,
            owed_delta=False,
        )
