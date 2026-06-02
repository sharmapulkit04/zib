"""diff_reference capability — surface the unconfirmed delta, read-only. (Query)

This is the read side of solution spec §9.2 (`zib diff <name>`): show *what changed*
between the agent's conformance baseline (``confirmed_through``) and the current pin,
without mutating anything. It never advances the baseline — so it can be re-run (and
pre-injected by the skill) freely, re-showing the still-unconfirmed delta until
``confirm`` closes it.

The range is **commit-anchored** at ``(confirmed_through.commit, pin.commit]`` — always
the immutable captured SHAs, never re-resolved labels (spec §9.2/§9.3). Three outcomes,
decided purely from the lock entry's own conformance state:

    confirmed_through is None        → first encounter: the agent reads the WHOLE reference
                                       (`zib cat`). read_whole=True, has_pending=True, delta=None.
    confirmed_through == pin commit   → caught up: nothing to apply. has_pending=False, delta=None.
    confirmed_through < pin commit    → owed delta: surface it. has_pending=True, delta computed,
                                       read_whole = (delta.magnitude is REWRITE) — the §9.2
                                       "substantial rewrite — re-read the whole reference" escape hatch.

Orchestration only — a Query capability that reads stores + a gateway process and returns
data. It mutates nothing and calls no other capability (CLAUDE.md invariants). ``source``
and ``subdirectory`` come from the manifest declaration; the conformance baseline and pin
come from the lock entry.

Pure stdlib + zib.core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import RefName
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.notes.translator.notes_types import Delta
from zib.core.ports.persistence.stores import LockfileStore, ManifestStore
from zib.core.rules.computation.delta.delta import Magnitude


@dataclass(frozen=True, slots=True)
class DiffResult:
    """The outcome of a read-only ``diff`` for one reference.

    ``has_pending`` is True whenever there is something for the agent to do — either an
    owed delta to apply, or a first encounter to read whole. ``read_whole`` is True when
    the agent should read the entire reference (`zib cat`) rather than apply a line-by-line
    delta: the first encounter (no baseline yet) or a major rewrite. ``delta`` carries the
    surfaced change; it is ``None`` for a first encounter (read whole instead) and when
    caught up (nothing to apply).
    """

    name: str
    has_pending: bool
    read_whole: bool
    delta: Delta | None


class DiffReference:
    """Surface the unconfirmed delta for one reference. Reads only — never mutates."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        notes_process: NotesProcess,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._notes = notes_process

    def execute(self, name: str) -> DiffResult:
        """Surface the delta for the reference named ``name``.

        Raises:
            ValueError: when ``name`` is not declared in the manifest or not pinned in the
                lockfile (there is nothing to diff).
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

        # First encounter — nothing confirmed yet. The agent reads the whole reference
        # (`zib cat`) rather than a delta; there is no baseline to diff against.
        if entry.confirmed_through is None:
            return DiffResult(
                name=name,
                has_pending=True,
                read_whole=True,
                delta=None,
            )

        # Caught up — the baseline already sits at the current pin. Nothing to apply.
        if entry.confirmed_through.commit == entry.pin.commit:
            return DiffResult(
                name=name,
                has_pending=False,
                read_whole=False,
                delta=None,
            )

        # Owed delta — surface the change across the SHA-immutable
        # (confirmed_through, pin] range. A REWRITE magnitude flips read_whole on
        # (§9.2 escape hatch): the agent re-reads the whole reference instead.
        delta = self._notes.delta(
            ref.source,
            entry.confirmed_through.commit,
            entry.pin.commit,
            ref.subdirectory,
        )
        return DiffResult(
            name=name,
            has_pending=True,
            read_whole=delta.magnitude is Magnitude.REWRITE,
            delta=delta,
        )
