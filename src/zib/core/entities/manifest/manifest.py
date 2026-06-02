"""Manifest aggregate — the developer's *declared intent* (``zib.toml``).

The manifest says what references this project wants and how to track them. It is
hand-editable; the lockfile (a separate aggregate) records the *resolved reality*.
Connected to the lockfile by RefName only — independent lifecycles.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from zib.core.entities.shared.value_objects import RefName, RefSpec, Role


class OnUpdate(str, Enum):
    """What polling does when a newer version exists (solution spec — [poll])."""

    REPORT = "report"  # surface that an update is available; do not change anything
    PULL = "pull"      # fetch + repin to the newer version (the agent still applies it)


@dataclass(frozen=True, slots=True)
class PollPolicy:
    """Optional per-reference or global polling policy. Absent = no polling."""

    on_update: OnUpdate = OnUpdate.REPORT


@dataclass(frozen=True, slots=True)
class ReferenceEntry:
    """One declared reference. Owned by the manifest; addressed by the root only."""

    name: RefName
    role: Role
    source: str               # owner/repo | url | local path — normalized at add time
    spec: RefSpec
    subdirectory: str | None = None
    description: str | None = None
    poll: PollPolicy | None = None


@dataclass(slots=True)
class Manifest:
    """Aggregate root over the declared references.

    Invariant: reference names are unique. External code talks to the root; entries are
    read-only from outside and reached via :meth:`by_name` / :meth:`by_role`.
    """

    references: list[ReferenceEntry] = field(default_factory=list)
    poll: PollPolicy | None = None  # global default; per-reference poll overrides it

    def __post_init__(self) -> None:
        self._assert_unique_names()

    def add(self, entry: ReferenceEntry) -> None:
        if self.by_name(entry.name) is not None:
            raise ValueError(f"reference {entry.name} already declared")
        self.references.append(entry)
        self._assert_unique_names()

    def remove(self, name: RefName) -> None:
        self.references = [r for r in self.references if r.name != name]

    def by_name(self, name: RefName) -> ReferenceEntry | None:
        return next((r for r in self.references if r.name == name), None)

    def by_role(self, role: Role) -> list[ReferenceEntry]:
        return [r for r in self.references if r.role == role]

    def _assert_unique_names(self) -> None:
        names = [r.name for r in self.references]
        if len(names) != len(set(names)):
            raise ValueError("reference names must be unique within a manifest")
