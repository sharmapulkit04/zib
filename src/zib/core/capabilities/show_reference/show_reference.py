"""show_reference capability (Query) — the full detail of one reference.

``zib show <name>`` answers "what exactly is this reference, and where does it
stand?" by joining the two aggregates a reference lives in: the manifest (the
*declared intent* — role, source, the tracked spec, optional subdirectory and
self-description) and the lockfile (the *resolved reality* — the display label,
the pinned commit, and the conformance baseline the agent confirmed through).

This is a Query: it reads, projects, and returns. No mutation, no persistence, no
agent-file writes (CLAUDE.md: a query orchestrates a read and hands back data; a
capability is still a capability when it is simple). It owns no business logic — the
only computation is turning the typed :class:`RefSpec` into a human-readable
``spec_repr`` string, which is pure presentation of the reference's own data, not a
domain decision (CLAUDE.md decision test: decidable from own data → here).

A reference that is *declared but not yet installed* has a manifest entry but no lock
entry. ``show`` still describes it fully from the manifest; the resolved/pinned fields
report that it is not installed rather than failing. A name that isn't declared at all
is a clear, named error — there is nothing to show.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import LockEntry
from zib.core.entities.manifest.manifest import ReferenceEntry
from zib.core.entities.shared.value_objects import RefKind, RefName, RefSpec
from zib.core.ports.persistence.stores import LockfileStore, ManifestStore

_NOT_INSTALLED = "not installed"


@dataclass(frozen=True, slots=True)
class RefDetail:
    """The full, joined detail of one reference — a value the shell formats.

    Declaration fields (``role``, ``source``, ``spec_repr``, ``subdirectory``,
    ``description``) come from the manifest. Resolution fields (``resolved``,
    ``pinned_commit``, ``confirmed_commit``) come from the lockfile, or report
    ``"not installed"`` / ``None`` when the reference is declared but not yet pinned.
    Frozen — a query result is read, never mutated.
    """

    name: str
    role: str
    source: str
    spec_repr: str
    resolved: str
    pinned_commit: str
    confirmed_commit: str | None
    subdirectory: str | None
    description: str | None


class ShowReference:
    """Join the manifest declaration and the lockfile pin into one :class:`RefDetail`."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store

    def execute(self, name: str) -> RefDetail:
        """Return the full detail for ``name``. Raises if it isn't declared.

        ``name`` arrives as a raw string and is validated into a :class:`RefName` at
        the boundary; an invalid name can't match a declared reference anyway. The
        manifest is the source of truth for existence — a missing declaration is the
        error, not a missing lock entry (a declared-but-uninstalled reference is a
        valid, describable state).
        """
        ref_name = RefName(name)

        manifest = self._manifest_store.read()
        reference = manifest.by_name(ref_name)
        if reference is None:
            raise ValueError(f"reference {name!r} is not declared; nothing to show")

        lock_entry = self._lockfile_store.read().get(ref_name)
        return _project(reference, lock_entry)


def _project(reference: ReferenceEntry, lock_entry: LockEntry | None) -> RefDetail:
    """Combine a manifest entry with its (optional) lock entry into a RefDetail."""
    if lock_entry is None:
        resolved = _NOT_INSTALLED
        pinned_commit = _NOT_INSTALLED
        confirmed_commit: str | None = None
    else:
        resolved = lock_entry.resolved
        pinned_commit = str(lock_entry.pin.commit)
        confirmed_commit = (
            None
            if lock_entry.confirmed_through is None
            else str(lock_entry.confirmed_through.commit)
        )

    return RefDetail(
        name=str(reference.name),
        role=str(reference.role),
        source=reference.source,
        spec_repr=_spec_repr(reference.spec),
        resolved=resolved,
        pinned_commit=pinned_commit,
        confirmed_commit=confirmed_commit,
        subdirectory=reference.subdirectory,
        description=reference.description,
    )


def _spec_repr(spec: RefSpec) -> str:
    """Render a typed :class:`RefSpec` as a stable, human-readable label.

    Pure presentation of the reference's own data — each kind keeps its tracking word
    so the agent can see *how* the reference is tracked, not just its value:

        SEMVER  '^2.1.0'  → 'version ^2.1.0'
        TAG     'v2.1.0'  → 'tag v2.1.0'
        BRANCH  'main'    → 'branch main'
        REV     '<sha>'   → 'rev <sha>'
        LATEST  (none)    → 'version latest'
    """
    if spec.kind is RefKind.LATEST:
        return "version latest"
    label = {
        RefKind.SEMVER: "version",
        RefKind.TAG: "tag",
        RefKind.BRANCH: "branch",
        RefKind.REV: "rev",
    }[spec.kind]
    return f"{label} {spec.value}"
