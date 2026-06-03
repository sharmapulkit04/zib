"""FileContentStore — the real :class:`ContentStore`, materializing under ``.zib/``.

Secondary adapter. Each reference's exported tree is written verbatim under
``<root>/.zib/references/<name>/<label>/``. ``read_tree`` walks that directory back into
:class:`TreeEntry` values and ``verify`` recomputes the canonical hash via the *same*
``content_hash`` rule the fetch process used — so a pin verifies iff the bytes on disk match.

The ``label`` (a tag like ``v2.1.0``, a branch like ``main``, a short sha, or a semver range
like ``^2.1.0``) is sanitized into a single safe path segment for the directory name; the
*tree entry paths* inside it are written exactly as exported, so the hash is unaffected by
the label sanitization. A small marker maps the sanitized segment back, but verification
never needs it — it just hashes whatever is on disk.

Modes are preserved: regular ``0o100644`` / executable ``0o100755`` files are written with
the matching POSIX permission bits; symlinks (``0o120000``) are written as real symlinks
whose target is the stored blob, so a round trip reproduces the exact mode the hash covers.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
from pathlib import Path

from zib.core.entities.shared.value_objects import (
    SYMLINK_MODE,
    ContentHash,
    RefName,
    TreeEntry,
)
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash

_REFERENCES_ROOT = Path(".zib") / "references"
# A sidecar recording the original repo-relative path of every file in a label dir, so
# read_tree reproduces the exact TreeEntry.path (and thus the exact hash) even though the
# on-disk layout could otherwise be ambiguous for odd paths. One line: "<octal mode> <path>".
_MANIFEST_NAME = ".zib-tree"


class FileContentStore:
    """Materializes/verifies reference trees under ``<root>/.zib/references/``."""

    def __init__(self, project_root: Path) -> None:
        """Bind the store to a project root; content lives under ``<root>/.zib/references``."""
        self._root = Path(project_root)

    def materialize(self, name: RefName, label: str, tree: list[TreeEntry]) -> None:
        """Write ``tree`` to ``.zib/references/<name>/<label>/`` (replacing any prior copy)."""
        target = self._label_dir(name, label)
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

        index_lines: list[str] = []
        for entry in tree:
            dest = target / entry.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if entry.mode == SYMLINK_MODE:
                link_target = entry.blob.decode("utf-8")
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                os.symlink(link_target, dest)
            else:
                dest.write_bytes(entry.blob)
                if entry.mode == 0o100755:
                    dest.chmod(0o755)
                else:
                    dest.chmod(0o644)
            index_lines.append(f"{entry.mode:o} {entry.path}")

        (target / _MANIFEST_NAME).write_text(
            "\n".join(index_lines) + ("\n" if index_lines else ""), encoding="utf-8"
        )

    def read_tree(self, name: RefName, label: str) -> list[TreeEntry]:
        """Reconstruct the :class:`TreeEntry` list from the materialized label dir."""
        target = self._label_dir(name, label)
        index = target / _MANIFEST_NAME
        if not index.is_file():
            raise KeyError(f"no materialized content for {name!s} @ {label!r}")
        entries: list[TreeEntry] = []
        for line in index.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            mode_str, _, path = line.partition(" ")
            mode = int(mode_str, 8)
            dest = target / path
            if mode == SYMLINK_MODE:
                blob = os.readlink(dest).encode("utf-8")
            else:
                blob = dest.read_bytes()
            entries.append(TreeEntry(path=path, mode=mode, blob=blob))
        return entries

    def verify(self, name: RefName, label: str, expected: ContentHash) -> bool:
        """True iff the materialized tree exists and hashes to ``expected``."""
        try:
            tree = self.read_tree(name, label)
        except (KeyError, FileNotFoundError):
            return False
        return compute_content_hash(tree) == expected

    def remove(self, name: RefName) -> None:
        """Delete all materialized labels for ``name`` (``.zib/references/<name>/``)."""
        ref_dir = self._root / _REFERENCES_ROOT / str(name)
        if ref_dir.exists():
            shutil.rmtree(ref_dir)

    # ------------------------------------------------------------------ internals

    def _label_dir(self, name: RefName, label: str) -> Path:
        return self._root / _REFERENCES_ROOT / str(name) / _safe_segment(label)


def _safe_segment(label: str) -> str:
    """Turn a resolved label into one filesystem-safe path segment.

    Distinct labels must map to distinct segments (so two pins never collide on disk), so any
    replaced run is suffixed-collapsed but the original is recoverable enough for humans —
    e.g. ``^2.1.0`` → ``_2.1.0``, ``feature/x`` → ``feature_x``.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", label)
    return cleaned or "_"
