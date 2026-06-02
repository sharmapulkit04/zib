"""GitPort — the driven boundary of the git gateway.

This is the "source-adapter seam" from the solution spec, expressed as a port. The git
gateway's processes (resolve / fetch / notes) orchestrate translators + rules and call
*this* to reach the outside world. Infrastructure implements it with the real git CLI
(``git ls-remote``, archive/checkout-index, ``git diff``, ``git log``, ``git for-each-ref``).

A future non-git source (URL, registry) is a *different* gateway with its own port —
core never learns which technology is behind this one. Methods return lightly-structured
data; the gateway's *translators* map that into domain vocabulary (semver pick, ref deref,
release-note interpretation). Infrastructure touches wire format only (CLAUDE.md invariant 8).

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry


@dataclass(frozen=True, slots=True)
class GitTag:
    """A tag name and the commit it points at (annotated tags already dereferenced)."""

    name: str
    commit: CommitSha


@dataclass(frozen=True, slots=True)
class GitCommit:
    """A commit in a log range — the per-commit change record for branch-tracked refs."""

    commit: CommitSha
    subject: str
    body: str


@runtime_checkable
class GitPort(Protocol):
    """Raw git operations against a source repo. All synchronous."""

    def list_tags(self, source: str) -> list[GitTag]:
        """Every release tag in the source, with annotated tags dereferenced to commits."""
        ...

    def resolve(self, source: str, ref: str) -> CommitSha:
        """Resolve a branch name / tag / rev to the commit it currently points at."""
        ...

    def export_tree(
        self, source: str, commit: CommitSha, subdirectory: str | None
    ) -> list[TreeEntry]:
        """Export the tree at ``commit`` (optionally scoped to ``subdirectory``) as files."""
        ...

    def diff(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> str:
        """Unified diff between two commits — the raw 'what changed' for the delta."""
        ...

    def log(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> list[GitCommit]:
        """Commit log in ``(from, to]`` — release notes stand-in for branch-tracked refs."""
        ...

    def tag_message(self, source: str, tag: str) -> str | None:
        """The annotated-tag message (producer's release notes), if any."""
        ...

    def is_ancestor(self, source: str, ancestor: CommitSha, descendant: CommitSha) -> bool:
        """True if ``ancestor`` is reachable from ``descendant`` (``git merge-base --is-ancestor``).

        Used to validate ``confirm --to`` recovery: a confirmed baseline may only be moved
        back to a commit that genuinely precedes the current pin.
        """
        ...
