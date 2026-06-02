"""fetch gateway DTOs — the domain-language result of a tree fetch.

The fetch interaction is outbound + synchronous: a capability asks for the tree at a
resolved commit, and gets back the materialized files plus the canonical content hash
that pins them. :class:`FetchedRef` is that result, carried in domain types only — the
``GitPort`` (infrastructure) deals in wire format; this is what the gateway hands core.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import ContentHash, TreeEntry


@dataclass(frozen=True, slots=True)
class FetchedRef:
    """An exported reference tree and its canonical content hash.

    ``tree`` is the list of files at the fetched commit (already scoped to the
    reference's subdirectory if any). ``content_hash`` is the attribute-blind
    ``sha256:<hex>`` over exactly that tree — the reproducibility anchor that
    becomes the pin's content hash.
    """

    tree: list[TreeEntry]
    content_hash: ContentHash
