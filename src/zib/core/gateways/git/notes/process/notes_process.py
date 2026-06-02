"""NotesProcess — the outbound notes gateway interaction (synchronous).

This is the gateway's "capability": a capability calls :meth:`delta` in domain
language ("give me what changed between these two pins") and gets back a domain
:class:`Delta`. The process orchestrates the git port and the gateway rules; it
holds no provider vocabulary itself.

Assembly (per the contract):

    diff_text    = port.diff(from, to)
    commits      = port.log(from, to)
    (f, ins, del)= parse_diff_counts(diff_text)
    lines_before = total newline count across the from-side exported tree blobs
    magnitude    = classify_magnitude(DiffStats(f, ins, del, lines_before))
    tag_notes    = port.tag_message(to_tag) if to_tag else None

``lines_before`` is the denominator for the churn ratio: it makes magnitude
relative to how much content existed *before* the change. A big diff against a
tiny baseline is a REWRITE; a small diff against a large baseline is INCREMENTAL.

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.shared.value_objects import CommitSha
from zib.core.gateways.git.notes.rules.diff_stats import parse_diff_counts
from zib.core.gateways.git.notes.translator.notes_types import Delta
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.rules.computation.delta.delta import (
    DiffStats,
    classify_magnitude,
)


class NotesProcess:
    """Builds a domain :class:`Delta` between two pins via the git port."""

    def __init__(self, git_port: GitPort) -> None:
        self._port = git_port

    def delta(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
        to_tag: str | None = None,
    ) -> Delta:
        """Assemble the 'what changed' Delta from ``from_commit`` to ``to_commit``."""
        diff_text = self._port.diff(source, from_commit, to_commit, subdirectory)
        commits = self._port.log(source, from_commit, to_commit, subdirectory)
        files_changed, insertions, deletions = parse_diff_counts(diff_text)

        from_tree = self._port.export_tree(source, from_commit, subdirectory)
        lines_before = sum(entry.blob.count(b"\n") for entry in from_tree)

        magnitude = classify_magnitude(
            DiffStats(
                files_changed=files_changed,
                insertions=insertions,
                deletions=deletions,
                lines_before=lines_before,
            )
        )

        tag_notes = self._port.tag_message(source, to_tag) if to_tag else None

        return Delta(
            diff_text=diff_text,
            commits=commits,
            magnitude=magnitude,
            tag_notes=tag_notes,
        )
