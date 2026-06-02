"""content_hash rule — the canonical, attribute-blind hash of an exported tree.

Pure function: tree entries in, ContentHash out. No filesystem, no git — the caller
(git gateway / content store) supplies the :class:`TreeEntry` list. That keeps this
exhaustively unit-testable and makes the pin reproducible byte-for-byte.

Canonical serialization (solution spec §6; decisions.md D6):
  * paths NFC-normalized, then sorted by their raw UTF-8 bytes (stable across locales/OSes)
  * file mode included (regular / executable / symlink) — it changes what the agent reads
  * each entry length-framed and null-delimited so no two distinct trees can collide
  * symlinks hashed by their target bytes, never dereferenced
  * empty directories contribute nothing (only files are entries)
  * blind to git metadata (author, date, commit) — reflects content, not how it was committed

Pure stdlib only — this is core/.
"""

from __future__ import annotations

import hashlib
import unicodedata
from typing import Iterable

from zib.core.entities.shared.value_objects import ContentHash, TreeEntry


def compute_content_hash(entries: Iterable[TreeEntry]) -> ContentHash:
    """Return the canonical ``sha256:<hex>`` content hash for an exported tree."""
    normalized: list[tuple[bytes, int, bytes]] = []
    for entry in entries:
        path_bytes = unicodedata.normalize("NFC", entry.path).encode("utf-8")
        normalized.append((path_bytes, entry.mode, entry.blob))

    # Sort by raw UTF-8 path bytes — independent of input order and of platform collation.
    normalized.sort(key=lambda item: item[0])

    digest = hashlib.sha256()
    for path_bytes, mode, blob in normalized:
        # Frame each field with its length + a null separator so concatenations are
        # unambiguous: no choice of paths/content can produce the same byte stream as
        # a different tree.
        digest.update(b"%d\0" % len(path_bytes))
        digest.update(path_bytes)
        digest.update(b"%o\0" % mode)
        digest.update(b"%d\0" % len(blob))
        digest.update(blob)

    return ContentHash("sha256:" + digest.hexdigest())
