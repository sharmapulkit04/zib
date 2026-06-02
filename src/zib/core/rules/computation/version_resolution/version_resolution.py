"""Resolve a manifest RefSpec to a concrete release tag.

This is the *semver/tag lane* of reference resolution (solution spec §6, step 1).
BRANCH and REV are commit-level and never touch the tag list — they are handled
by ``ResolveProcess``, not here. So this rule covers exactly the three tag-backed
kinds:

* ``SEMVER`` — parse ``spec.value`` as a constraint :class:`Range`, then among the
  tags whose name parses as a semver version pick the **highest** one satisfying it.
  An exact pin (``"2.1.4"``) is just a degenerate range matching one version.
* ``LATEST`` — the highest **stable** (non-prerelease) version tag, ignoring the
  constraint entirely (modelled as the ``*`` wildcard range, which excludes
  prereleases by construction).
* ``TAG`` — a *literal* tag: the GitTag whose ``name`` equals ``spec.value`` exactly.
  No semver interpretation; the producer's tag string is taken as-is.

For SEMVER/LATEST, an empty result is an error — either no tag satisfies the
range or there are no semver-parseable tags at all (the "unresolvable version"
case from §10). The raised :class:`ValueError` names the constraint so the CLI
can report it verbatim.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.shared.semver import Range
from zib.core.entities.shared.value_objects import RefKind, RefSpec
from zib.core.gateways.git.port.git_port import GitTag
from zib.core.rules.computation.version_resolution.highest_tag import (
    highest_satisfying_tag,
)


def resolve_version(spec: RefSpec, tags: list[GitTag]) -> GitTag:
    """Resolve ``spec`` against ``tags`` to the single GitTag it selects.

    Only ``SEMVER`` / ``LATEST`` / ``TAG`` are valid here — any other kind is a
    programming error (BRANCH/REV are resolved by the process, not this rule).

    Raises:
        ValueError: if the kind is not tag-backed, or if a SEMVER/LATEST
            constraint is satisfied by no available tag.
    """
    if spec.kind not in (RefKind.SEMVER, RefKind.LATEST, RefKind.TAG):
        raise ValueError(
            f"resolve_version handles only semver/latest/tag, got {spec.kind.value!r}"
        )

    if spec.kind is RefKind.TAG:
        for tag in tags:
            if tag.name == spec.value:
                return tag
        raise ValueError(f"tag {spec.value!r} not found among available tags")

    if spec.kind is RefKind.LATEST:
        rng = Range.from_spec("*")  # any stable version; excludes prereleases
        constraint = "latest"
    else:  # SEMVER
        rng = Range.from_spec(spec.value)  # type: ignore[arg-type]
        constraint = spec.value  # type: ignore[assignment]

    winner = highest_satisfying_tag(tags, rng)
    if winner is None:
        raise ValueError(f"no available tag satisfies version constraint {constraint!r}")
    return winner
