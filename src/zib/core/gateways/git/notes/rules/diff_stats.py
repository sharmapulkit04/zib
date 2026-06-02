"""Parse a unified diff into raw change counts — a gateway-specific pure rule.

The notes gateway turns "what changed between two pins" into a domain Delta. Part
of that is the *size* of the change, which feeds the magnitude classification
(REWRITE vs INCREMENTAL). The raw diff text comes from the git port; this rule
reduces it to three integers without any knowledge of trees or commits.

Counting rules (deliberately simple and deterministic):

  - files_changed: number of ``diff --git`` headers — one per file git touched.
  - insertions:    lines beginning with ``+`` that are NOT the ``+++`` file header.
  - deletions:     lines beginning with ``-`` that are NOT the ``---`` file header.

Hunk headers (``@@ ... @@``), index lines, and mode lines are ignored because they
start with neither ``+`` nor ``-`` (``@``, ``i``, ``o``, ``n``, ``d`` …). The
``+++``/``---`` guard is the one subtlety: those file headers must not be miscounted
as content changes.

Pure: only operates on the given string. No I/O, no third-party imports.
"""

from __future__ import annotations

_DIFF_HEADER = "diff --git"


def parse_diff_counts(unified_diff: str) -> tuple[int, int, int]:
    """Reduce a unified diff to ``(files_changed, insertions, deletions)``.

    ``files_changed`` counts ``diff --git`` headers. ``insertions`` counts ``+``
    content lines (excluding the ``+++`` file header); ``deletions`` counts ``-``
    content lines (excluding the ``---`` file header). An empty diff is ``(0, 0, 0)``.
    """
    files_changed = 0
    insertions = 0
    deletions = 0

    for line in unified_diff.splitlines():
        if line.startswith(_DIFF_HEADER):
            files_changed += 1
            continue
        if line.startswith("+++") or line.startswith("---"):
            # File headers — not content. Guard before the +/- content checks.
            continue
        if line.startswith("+"):
            insertions += 1
        elif line.startswith("-"):
            deletions += 1

    return (files_changed, insertions, deletions)
