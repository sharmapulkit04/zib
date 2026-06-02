"""FetchProcess — the outbound, synchronous "fetch the tree at a commit" interaction.

A capability has a resolved commit (from the resolve interaction) and wants the actual
files plus a reproducible pin over them. This process orchestrates that:

    export the tree at the commit (via the git port)  ->  hash it canonically (content_hash rule)

It speaks domain language (``fetch(...) -> FetchedRef``), calls the ``GitPort`` outward, and
returns the result directly — no async lifecycle, so no gateway entity or repository. The
hashing is the shared ``content_hash`` rule, so the pin computed here is byte-for-byte
identical to what the content store verifies later.

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.shared.value_objects import CommitSha
from zib.core.gateways.git.fetch.translator.fetch_types import FetchedRef
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash


class FetchProcess:
    """Outbound git interaction: export and hash the tree at a resolved commit."""

    def __init__(self, git_port: GitPort) -> None:
        self._git_port = git_port

    def fetch(
        self, source: str, commit: CommitSha, subdirectory: str | None
    ) -> FetchedRef:
        """Export the tree at ``commit`` (scoped to ``subdirectory``) and pin it by content."""
        tree = self._git_port.export_tree(source, commit, subdirectory)
        content_hash = compute_content_hash(tree)
        return FetchedRef(tree=tree, content_hash=content_hash)
