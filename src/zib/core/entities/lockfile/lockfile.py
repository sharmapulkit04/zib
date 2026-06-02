"""Lockfile aggregate root — the set of pinned references (``zib.lock``).

Records resolved reality and the conformance baselines. Connected to the manifest by
RefName only. ``lockfile_version`` is the schema version of the file format, bumped only
when the on-disk shape changes (so a newer zib can read/migrate an older lock).

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zib.core.entities.lockfile.lock_entry import LockEntry
from zib.core.entities.shared.value_objects import RefName

CURRENT_LOCKFILE_VERSION = 1


@dataclass(slots=True)
class Lockfile:
    """Aggregate root over LockEntry, keyed by reference name.

    Invariant: one entry per name (the dict enforces it). External code mutates entries
    only through this root or through an entry's own behavioral methods.
    """

    lockfile_version: int = CURRENT_LOCKFILE_VERSION
    entries: dict[str, LockEntry] = field(default_factory=dict)

    def get(self, name: RefName) -> LockEntry | None:
        return self.entries.get(str(name))

    def put(self, entry: LockEntry) -> None:
        """Insert or replace the entry for a name (used by add / swap / repin flows)."""
        self.entries[str(entry.name)] = entry

    def remove(self, name: RefName) -> None:
        self.entries.pop(str(name), None)

    def __iter__(self):
        return iter(self.entries.values())

    def __len__(self) -> int:
        return len(self.entries)
