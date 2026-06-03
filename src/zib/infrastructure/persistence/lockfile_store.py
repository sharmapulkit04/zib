"""TomlLockfileStore — the real :class:`LockfileStore`, backed by ``zib.lock``.

Secondary adapter. The lockfile is zib's output, not hand-edited, so (unlike the manifest)
this emits a *canonical* document: a fixed key order, entries sorted by name. That makes the
file diff cleanly and lets the adapter honor the port's compare-before-write contract — a
re-run that resolves to the same pins rewrites nothing.

On-disk shape::

    lockfile_version = 1

    [[reference]]
    name = "hex"
    ref_type = "branch"
    resolved = "main"
    commit = "<40 hex>"
    content_hash = "sha256:<64 hex>"
    confirmed_commit = "<40 hex>"        # optional — present only when confirmed
    confirmed_content_hash = "sha256:..."  # paired with confirmed_commit
"""

from __future__ import annotations

from pathlib import Path

import tomlkit

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import CURRENT_LOCKFILE_VERSION, Lockfile
from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
)

LOCKFILE_FILENAME = "zib.lock"


class TomlLockfileStore:
    """Reads/writes ``<root>/zib.lock`` as a :class:`Lockfile`, canonical + idempotent."""

    def __init__(self, project_root: Path) -> None:
        """Bind the store to a project root. The lockfile lives at ``<root>/zib.lock``."""
        self._path = Path(project_root) / LOCKFILE_FILENAME

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> Lockfile:
        """Parse ``zib.lock`` into a :class:`Lockfile`. Absent file → default empty lock."""
        if not self._path.is_file():
            return Lockfile()
        doc = tomlkit.parse(self._path.read_text(encoding="utf-8"))
        lock = Lockfile(
            lockfile_version=int(doc.get("lockfile_version", CURRENT_LOCKFILE_VERSION))
        )
        for table in doc.get("reference", []):
            lock.put(_entry_from_table(table))
        return lock

    def write(self, lockfile: Lockfile) -> None:
        """Emit a canonical ``zib.lock``. Compare-before-write: no-op if unchanged."""
        rendered = self._render(lockfile)
        if self._path.is_file() and self._path.read_text(encoding="utf-8") == rendered:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(rendered, encoding="utf-8")

    @staticmethod
    def _render(lockfile: Lockfile) -> str:
        doc = tomlkit.document()
        doc["lockfile_version"] = lockfile.lockfile_version
        array = tomlkit.aot()
        for entry in sorted(lockfile, key=lambda e: str(e.name)):
            array.append(_table_from_entry(entry))
        doc["reference"] = array
        return tomlkit.dumps(doc)


# ----------------------------------------------------------------------- mapping helpers


def _entry_from_table(table) -> LockEntry:
    pin = Pin(
        commit=CommitSha(str(table["commit"])),
        content_hash=ContentHash(str(table["content_hash"])),
    )
    confirmed = None
    if "confirmed_commit" in table:
        confirmed = Pin(
            commit=CommitSha(str(table["confirmed_commit"])),
            content_hash=ContentHash(str(table["confirmed_content_hash"])),
        )
    return LockEntry(
        name=RefName(str(table["name"])),
        ref_type=RefKind(str(table["ref_type"])),
        resolved=str(table["resolved"]),
        pin=pin,
        confirmed_through=confirmed,
    )


def _table_from_entry(entry: LockEntry):
    table = tomlkit.table()
    table["name"] = str(entry.name)
    table["ref_type"] = entry.ref_type.value
    table["resolved"] = entry.resolved
    table["commit"] = entry.pin.commit.value
    table["content_hash"] = entry.pin.content_hash.value
    if entry.confirmed_through is not None:
        table["confirmed_commit"] = entry.confirmed_through.commit.value
        table["confirmed_content_hash"] = entry.confirmed_through.content_hash.value
    return table
