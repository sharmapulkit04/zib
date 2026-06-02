"""Constraint drift — does a higher version exist, and is it in-range or beyond?

This rule answers the ``outdated`` poll for the two *resolving* version lanes
(``semver`` and ``latest``), comparing the **currently pinned** version against
the live tag list. It is a pure function of ``(live spec, current resolved
version, available tags)`` — it reads no stored original constraint and never
re-pins (changing a version is always ``update``/``upgrade``'s job, §10).

Three outcomes, mirroring the package-manager consume split (§8.4):

* :data:`DriftStatus.UPDATE_AVAILABLE` — a newer version **inside** the
  constraint exists. ``update`` (in-range, lockfile-only) would take it.
  ``target`` is the highest such in-range version.
* :data:`DriftStatus.UPGRADE_AVAILABLE` — no newer in-range version, but a
  newer version exists **outside** the constraint. ``upgrade`` (jump to latest,
  rewrites the constraint) would take it. ``target`` is the highest version
  overall.
* :data:`DriftStatus.UP_TO_DATE` — nothing newer than the current pin. ``target``
  is ``None``.

Scope: ``SEMVER`` and ``LATEST`` only. ``TAG`` (literal), ``BRANCH`` (tracking
tip) and ``REV`` (frozen) are not version-resolved, so drift for them is the
capability's concern, not this rule's — this rule raises ``ValueError`` for
those kinds rather than guess.

Prereleases follow the semver module's gate: they are excluded from a stable
constraint, and from the ``latest`` comparison, unless the spec itself named a
prerelease (then the range admits them). The current pin is parsed the same way.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from zib.core.entities.shared.semver import Range, Version, highest_satisfying
from zib.core.entities.shared.value_objects import RefKind, RefSpec
from zib.core.gateways.git.port.git_port import GitTag


class DriftStatus(Enum):
    """Where the current pin sits relative to what's available upstream."""

    UP_TO_DATE = "up_to_date"               # nothing newer than the current pin
    UPDATE_AVAILABLE = "update_available"   # newer in-range version → `update`
    UPGRADE_AVAILABLE = "upgrade_available"  # newer only out-of-range → `upgrade`


@dataclass(frozen=True, slots=True)
class DriftResult:
    """The drift verdict and the version that would be taken (``None`` if none)."""

    status: DriftStatus
    target: str | None


def assess_drift(spec: RefSpec, current: str, available: list[GitTag]) -> DriftResult:
    """Assess drift for a ``SEMVER`` / ``LATEST`` ref against the live tag list.

    ``current`` is the version currently resolved/pinned (a tag name like
    ``"2.1.4"`` or ``"v2.1.4"``). ``available`` is every release tag in the
    source. Returns a :class:`DriftResult`; raises ``ValueError`` for any other
    ref kind or an unparseable ``current``.
    """
    if spec.kind not in (RefKind.SEMVER, RefKind.LATEST):
        raise ValueError(
            f"assess_drift handles only SEMVER/LATEST refs; got {spec.kind.value}"
        )

    current_version = Version.parse(current)
    if current_version is None:
        raise ValueError(f"current version {current!r} is not a parseable semver")

    # Parse the tag list into versions, dropping anything that isn't a version
    # (release repos can carry non-semver tags; they never participate in drift).
    versions = [v for v in (Version.parse(tag.name) for tag in available) if v is not None]

    if spec.kind is RefKind.LATEST:
        return _assess_latest(current_version, versions)
    return _assess_semver(spec, current_version, versions)


def _assess_latest(current: Version, versions: list[Version]) -> DriftResult:
    """LATEST tracks the highest stable version; any higher one is an update."""
    # `latest` follows stable releases unless the current pin is itself a
    # prerelease, mirroring the semver module's prerelease gate.
    candidates = [
        v for v in versions if v.is_stable or not current.is_stable
    ]
    higher = [v for v in candidates if v > current]
    if not higher:
        return DriftResult(DriftStatus.UP_TO_DATE, None)
    return DriftResult(DriftStatus.UPDATE_AVAILABLE, str(max(higher)))


def _assess_semver(spec: RefSpec, current: Version, versions: list[Version]) -> DriftResult:
    """SEMVER: prefer a newer in-range version; else flag an out-of-range upgrade."""
    rng = Range.from_spec(spec.value or "")

    # In-range: the highest version the constraint admits, if it beats the pin.
    in_range_best = highest_satisfying(versions, rng)
    if in_range_best is not None and in_range_best > current:
        return DriftResult(DriftStatus.UPDATE_AVAILABLE, str(in_range_best))

    # Out-of-range: a newer version exists overall but the constraint forbids it
    # → only `upgrade` (which rewrites the constraint) can take it. Compare
    # against stable versions unless the current pin is itself a prerelease.
    overall_candidates = [
        v for v in versions if v.is_stable or not current.is_stable
    ]
    higher_overall = [v for v in overall_candidates if v > current]
    if higher_overall:
        return DriftResult(DriftStatus.UPGRADE_AVAILABLE, str(max(higher_overall)))

    return DriftResult(DriftStatus.UP_TO_DATE, None)
