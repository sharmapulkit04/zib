"""Domain result type for the git RESOLVE interaction.

``ResolvedRef`` is what :class:`ResolveProcess` returns to its caller — a commit
paired with the human-readable *label* it resolved through (a version tag name, a
branch name, or a short SHA) and the :class:`RefKind` that produced it. This is the
domain vocabulary the resolve process speaks; infrastructure never sees it.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import CommitSha, RefKind


@dataclass(frozen=True, slots=True)
class ResolvedRef:
    """The outcome of resolving a :class:`RefSpec` against a source repo.

    Attributes:
        commit: the concrete 40-hex commit the spec resolved to (the immutable pin).
        label: the name the resolution went through — a tag name (semver/latest/tag),
            a branch name (branch), or the short SHA (rev). This is what a human and
            the agent read as "what got pinned".
        ref_type: the :class:`RefKind` that drove the resolution.
    """

    commit: CommitSha
    label: str
    ref_type: RefKind
