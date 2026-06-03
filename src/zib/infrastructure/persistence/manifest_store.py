"""TomlManifestStore — the real :class:`ManifestStore`, backed by ``zib.toml``.

Secondary adapter (CLAUDE.md). It maps the on-disk TOML to the :class:`Manifest`
aggregate and back, touching wire format only — the domain decisions (which ref keys are
mutually exclusive, what a valid name is) live in the value objects the manifest holds.

Formatting preservation: reads with ``tomlkit`` and, on write, mutates the *same* parsed
document when one exists on disk, so the developer's comments / key order / whitespace
survive a round trip. A brand-new file is emitted from a fresh tomlkit document.

The on-disk shape (one ``[[reference]]`` array-of-tables per reference)::

    [[reference]]
    name = "hex"
    role = "architecture"
    source = "/path/or/url"
    version = "^2.1.0"          # exactly one of version/branch/tag/rev
    subdirectory = "docs"        # optional
    description = "..."          # optional

    [poll]                       # optional global poll policy
    on_update = "report"
"""

from __future__ import annotations

from pathlib import Path

import tomlkit

from zib.core.entities.manifest.manifest import (
    Manifest,
    OnUpdate,
    PollPolicy,
    ReferenceEntry,
)
from zib.core.entities.shared.value_objects import RefKind, RefName, RefSpec, Role

MANIFEST_FILENAME = "zib.toml"


class TomlManifestStore:
    """Reads/writes ``<root>/zib.toml`` as a :class:`Manifest`, preserving user formatting."""

    def __init__(self, project_root: Path) -> None:
        """Bind the store to a project root. The manifest lives at ``<root>/zib.toml``."""
        self._path = Path(project_root) / MANIFEST_FILENAME

    def exists(self) -> bool:
        return self._path.is_file()

    def read(self) -> Manifest:
        """Parse ``zib.toml`` into a :class:`Manifest`. Absent file → empty manifest."""
        if not self._path.is_file():
            return Manifest()
        doc = tomlkit.parse(self._path.read_text(encoding="utf-8"))
        references: list[ReferenceEntry] = []
        for table in doc.get("reference", []):
            references.append(_entry_from_table(table))
        poll = _poll_from_table(doc.get("poll"))
        return Manifest(references=references, poll=poll)

    def write(self, manifest: Manifest) -> None:
        """Serialize ``manifest`` to ``zib.toml``, preserving formatting where possible.

        Compare-before-write: if the rendered TOML is byte-identical to what is on disk, the
        file is left untouched (clean diffs / idempotency).
        """
        doc = (
            tomlkit.parse(self._path.read_text(encoding="utf-8"))
            if self._path.is_file()
            else tomlkit.document()
        )

        # Rebuild the [[reference]] array from the aggregate. We replace the whole array (the
        # aggregate is the source of truth for the reference set), but reuse the document so
        # top-level comments / non-reference tables survive.
        ref_array = tomlkit.aot()
        for entry in manifest.references:
            ref_array.append(_table_from_entry(entry))
        doc["reference"] = ref_array

        if manifest.poll is not None:
            poll_tbl = tomlkit.table()
            poll_tbl["on_update"] = manifest.poll.on_update.value
            doc["poll"] = poll_tbl
        elif "poll" in doc:
            del doc["poll"]

        rendered = tomlkit.dumps(doc)
        if self._path.is_file() and self._path.read_text(encoding="utf-8") == rendered:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(rendered, encoding="utf-8")


# ----------------------------------------------------------------------- mapping helpers


def _entry_from_table(table) -> ReferenceEntry:
    """Map one ``[[reference]]`` table to a :class:`ReferenceEntry`."""
    spec = RefSpec.from_manifest(
        version=table.get("version"),
        branch=table.get("branch"),
        tag=table.get("tag"),
        rev=table.get("rev"),
    )
    return ReferenceEntry(
        name=RefName(str(table["name"])),
        role=Role(str(table["role"])),
        source=str(table["source"]),
        spec=spec,
        subdirectory=_opt_str(table.get("subdirectory")),
        description=_opt_str(table.get("description")),
        poll=_poll_from_table(table.get("poll")),
    )


def _table_from_entry(entry: ReferenceEntry):
    """Map a :class:`ReferenceEntry` to a tomlkit table (stable key order)."""
    table = tomlkit.table()
    table["name"] = str(entry.name)
    table["role"] = str(entry.role)
    table["source"] = entry.source
    key, value = _spec_to_key(entry.spec)
    table[key] = value
    if entry.subdirectory is not None:
        table["subdirectory"] = entry.subdirectory
    if entry.description is not None:
        table["description"] = entry.description
    if entry.poll is not None:
        poll_tbl = tomlkit.table()
        poll_tbl["on_update"] = entry.poll.on_update.value
        table["poll"] = poll_tbl
    return table


def _spec_to_key(spec: RefSpec) -> tuple[str, str]:
    """Collapse a :class:`RefSpec` back to its single manifest key/value.

    Inverse of :meth:`RefSpec.from_manifest`. LATEST and SEMVER both live under the
    ``version`` key (``"latest"`` vs a range/exact), mirroring the manifest's version lane.
    """
    if spec.kind is RefKind.LATEST:
        return "version", "latest"
    if spec.kind is RefKind.SEMVER:
        return "version", spec.value  # type: ignore[return-value]
    if spec.kind is RefKind.TAG:
        return "tag", spec.value  # type: ignore[return-value]
    if spec.kind is RefKind.BRANCH:
        return "branch", spec.value  # type: ignore[return-value]
    return "rev", spec.value  # type: ignore[return-value]


def _poll_from_table(table) -> PollPolicy | None:
    """Map an optional ``[poll]`` table to a :class:`PollPolicy`."""
    if table is None:
        return None
    on_update = str(table.get("on_update", OnUpdate.REPORT.value))
    return PollPolicy(on_update=OnUpdate(on_update))


def _opt_str(value) -> str | None:
    return None if value is None else str(value)
