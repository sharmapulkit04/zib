"""Pick the highest GitTag whose name is a semver satisfying a constraint.

Sub-rule of :mod:`version_resolution`. Pure: given a list of tags and a parsed
:class:`Range`, return the tag carrying the greatest satisfying version, or
``None`` when nothing matches. Tag names that do not parse as a semver version
(``v`` prefix accepted, per :class:`Version`) are simply ignored here — the
orchestrator decides whether an empty result is an error.

Earns its own file because it is the one piece of real logic in resolution that
benefits from exhaustive, independent tests (tie-break by highest version,
``v``-prefix tolerance, prerelease exclusion) without dragging in RefSpec/kind
plumbing.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from zib.core.entities.shared.semver import Range, Version, highest_satisfying
from zib.core.gateways.git.port.git_port import GitTag


def highest_satisfying_tag(tags: list[GitTag], rng: Range) -> "GitTag | None":
    """Return the GitTag with the highest semver version satisfying ``rng``.

    Only tags whose ``name`` parses as a :class:`Version` are considered. Ties
    cannot occur — equal versions on distinct tag names are coalesced and the
    first registered wins, but in practice tag names map one-to-one to versions.
    Returns ``None`` if no parseable tag satisfies the range.
    """
    parsed: dict[Version, GitTag] = {}
    for tag in tags:
        version = Version.parse(tag.name)
        if version is None:
            continue
        # Keep the first tag seen for a given version (deterministic, stable).
        parsed.setdefault(version, tag)
    winner = highest_satisfying(parsed.keys(), rng)
    if winner is None:
        return None
    return parsed[winner]
