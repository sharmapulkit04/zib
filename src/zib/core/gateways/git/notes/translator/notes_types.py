"""Delta — the domain result of the notes gateway interaction.

This is the "what changed" surface the agent reads on update (solution spec §9):
the unified diff, the per-commit log (release-note stand-in for branch-tracked
refs), a magnitude verdict (INCREMENTAL vs REWRITE), and the producer's annotated
release notes if the new pin is a tag.

It is a frozen domain carrier — no behavior, no provider vocabulary. The
``NotesProcess`` assembles it from the git port's raw outputs via the gateway's
translator + rules.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.gateways.git.port.git_port import GitCommit
from zib.core.rules.computation.delta.delta import Magnitude


@dataclass(frozen=True)
class Delta:
    """The assembled 'what changed' between two pins.

    ``diff_text`` is the raw unified diff. ``commits`` is the log in ``(from, to]``.
    ``magnitude`` is the churn verdict. ``tag_notes`` is the annotated-tag message
    of the to-side tag, present only when the new pin resolved from a tag.
    """

    diff_text: str
    commits: list[GitCommit]
    magnitude: Magnitude
    tag_notes: str | None
