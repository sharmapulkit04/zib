"""ResolveProcess — the outbound RESOLVE interaction of the git gateway.

A capability hands this a ``source`` and a :class:`RefSpec` ("track ^2.1.0", "track
the ``main`` branch", "freeze at this rev") and gets back a single concrete
:class:`ResolvedRef`. The process orchestrates the resolution rule and the raw
:class:`GitPort`; it speaks domain language outward and never leaks git wire format.

Resolution branches on the spec's :class:`RefKind`:

* ``SEMVER`` / ``LATEST`` / ``TAG`` — tag-backed. Pull the source's tag list once and
  delegate the *pick* to :func:`resolve_version` (highest-in-range / newest stable /
  literal match). The label is the chosen tag's name.
* ``BRANCH`` — resolve the branch name to its current tip commit. The label is the
  branch name (the moving pointer the user named).
* ``REV`` — resolve the frozen SHA to itself. The label is the short SHA, since a rev
  has no human name to show.

Sync and side-effect free beyond the port read. Errors from the rule (no satisfying
tag) and the port (unknown branch/rev) propagate unchanged.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.shared.value_objects import RefKind, RefSpec
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.gateways.git.resolve.translator.resolve_types import ResolvedRef
from zib.core.rules.computation.version_resolution.version_resolution import (
    resolve_version,
)


class ResolveProcess:
    """Resolve a :class:`RefSpec` against a git source to a concrete :class:`ResolvedRef`."""

    def __init__(self, git_port: GitPort) -> None:
        self._git = git_port

    def resolve(self, source: str, spec: RefSpec) -> ResolvedRef:
        """Resolve ``spec`` against ``source`` to the commit + label it selects.

        Raises:
            ValueError: when a SEMVER/LATEST/TAG spec is satisfied by no available tag
                (propagated from :func:`resolve_version`).
            KeyError: when a BRANCH/REV name is unknown to the source (propagated from
                the git port).
        """
        if spec.kind in (RefKind.SEMVER, RefKind.LATEST, RefKind.TAG):
            tags = self._git.list_tags(source)
            chosen = resolve_version(spec, tags)
            return ResolvedRef(
                commit=chosen.commit, label=chosen.name, ref_type=spec.kind
            )

        if spec.kind is RefKind.BRANCH:
            commit = self._git.resolve(source, spec.value)  # type: ignore[arg-type]
            return ResolvedRef(
                commit=commit, label=spec.value, ref_type=RefKind.BRANCH  # type: ignore[arg-type]
            )

        # REV — frozen commit, labelled by its short SHA.
        commit = self._git.resolve(source, spec.value)  # type: ignore[arg-type]
        return ResolvedRef(commit=commit, label=commit.short(), ref_type=RefKind.REV)
