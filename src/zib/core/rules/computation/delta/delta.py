"""Magnitude classification for a delta between two pinned trees.

Spec §9.2: an update whose change is too large to be a meaningful increment is
a "major rewrite" — the agent is told to re-read the whole reference
(`zib cat <name>`) rather than apply line-by-line. This rule is the
deterministic size test behind that escape hatch.

The classification is pure churn: how much of the prior content was touched.
churn = (insertions + deletions) / max(lines_before, 1)
A churn at or above `threshold` (default 0.5 — half the prior lines changed)
is a REWRITE; anything below is INCREMENTAL.

Pure: only `dataclasses` and `enum`. No I/O, no third-party imports.
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class DiffStats:
    """Raw size of a diff between two trees.

    `lines_before` is the line count of the baseline (from-side) tree; it is
    the denominator for the churn ratio so the magnitude is relative to how
    much content existed before the change, not the absolute diff size.
    """

    files_changed: int
    insertions: int
    deletions: int
    lines_before: int


class Magnitude(Enum):
    """Whether a delta is a meaningful increment or a wholesale rewrite."""

    INCREMENTAL = "incremental"
    REWRITE = "rewrite"


def classify_magnitude(stats: DiffStats, *, threshold: float = 0.5) -> Magnitude:
    """Classify a diff as INCREMENTAL or REWRITE by churn ratio.

    churn = (insertions + deletions) / max(lines_before, 1)

    `max(lines_before, 1)` guards against division by zero when the baseline
    tree was empty; in that case any non-empty change is full churn (>= 1.0)
    and classifies as REWRITE, while a zero-change diff stays INCREMENTAL.

    The boundary is inclusive: churn exactly == threshold is a REWRITE.
    """
    churn = (stats.insertions + stats.deletions) / max(stats.lines_before, 1)
    if churn >= threshold:
        return Magnitude.REWRITE
    return Magnitude.INCREMENTAL
