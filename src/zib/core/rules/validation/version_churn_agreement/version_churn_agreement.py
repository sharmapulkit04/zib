"""version_churn_agreement — cross-check the declared version bump against measured churn.

decisions.md DS5. A SemVer version number is a *promise* about how much changed
(patch = fix, minor = feature, major = breaking), but the promise is unenforced and routinely
violated. zib already *measures* the actual change as a churn magnitude
(``delta.classify_magnitude`` -> INCREMENTAL | REWRITE). This rule compares the promise to the
measurement and flags the one dangerous disagreement: a sub-major bump (the version says
"nothing breaks") whose content was effectively **rewritten**. That is a likely SemVer
violation — the agent should distrust the version and re-read the whole reference rather than
apply a line-by-line delta.

It is allowed in core and stays "dumb" (DS4) because it reads only data zib already owns — two
version labels it pinned and a churn verdict it computed — never the *meaning* of the
reference's prose.

The rule is the canonical fractal: a sub-rule that classifies the bump, a sub-rule that maps
(bump, churn) to a verdict, and a thin orchestrator that composes them.

    classify_bump(from_label, to_label) -> BumpLevel        # SemVer increment between two labels
    verdict_for(bump, churn)            -> Verdict           # the (bump, churn) decision table
    assess_version_churn(from, to, churn) -> Verdict          # orchestrator

Only the *under-promise* direction is flagged. Over-promising (a tiny change tagged MAJOR) is
harmless — the agent is merely told "this may break" — so it reports CONSISTENT, not a warning
(minimalism: include nothing the problem doesn't require).

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from enum import Enum

from zib.core.entities.shared.semver import Version
from zib.core.rules.computation.delta.delta import Magnitude


class BumpLevel(Enum):
    """The SemVer increment between two version labels, by core (major.minor.patch)."""

    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"
    NONE = "none"        # same core, a downgrade, or only a prerelease differs — no forward bump
    UNKNOWN = "unknown"  # at least one label is not SemVer (a branch tip, a non-semver tag)


class Verdict(Enum):
    """The cross-check outcome."""

    CONSISTENT = "consistent"          # the version's promise matches the measured change
    UNDER_PROMISED = "under_promised"  # version claims less than measured -> distrust it, read fresh
    INAPPLICABLE = "inapplicable"      # no SemVer bump to check against (branch / non-semver / no bump)


def classify_bump(from_label: str, to_label: str) -> BumpLevel:
    """Classify the SemVer bump from ``from_label`` to ``to_label`` by core components.

    UNKNOWN when either label is not parseable SemVer (e.g. a branch name) — the BRANCH
    degradation path of DS5, where there is no version signal at all. NONE when the target does
    not advance the core triple (same version, a downgrade, or a prerelease-only change), since
    none of those is a forward release bump the churn can be checked against. Otherwise the
    highest-order component that increased decides MAJOR > MINOR > PATCH.
    """
    a = Version.parse(from_label)
    b = Version.parse(to_label)
    if a is None or b is None:
        return BumpLevel.UNKNOWN
    if b.major > a.major:
        return BumpLevel.MAJOR
    if b.major == a.major:
        if b.minor > a.minor:
            return BumpLevel.MINOR
        if b.minor == a.minor and b.patch > a.patch:
            return BumpLevel.PATCH
    return BumpLevel.NONE


def verdict_for(bump: BumpLevel, churn: Magnitude) -> Verdict:
    """Map a (declared bump, measured churn) pair to a cross-check verdict.

    The decision table:

        bump \\ churn     INCREMENTAL     REWRITE
        PATCH            CONSISTENT      UNDER_PROMISED
        MINOR            CONSISTENT      UNDER_PROMISED
        MAJOR            CONSISTENT      CONSISTENT          (major already warns of a big change)
        NONE / UNKNOWN   INAPPLICABLE    INAPPLICABLE        (no SemVer bump to check against)

    The only flag is a sub-major bump that nonetheless measured as a REWRITE — the version
    under-promised the change (a likely SemVer violation), so the agent should treat it as a
    rewrite and re-read the whole reference. An INCREMENTAL churn is consistent with any bump;
    over-promising (a small change under MAJOR) is harmless and stays CONSISTENT.
    """
    if bump in (BumpLevel.UNKNOWN, BumpLevel.NONE):
        return Verdict.INAPPLICABLE
    if churn is Magnitude.REWRITE and bump is not BumpLevel.MAJOR:
        return Verdict.UNDER_PROMISED
    return Verdict.CONSISTENT


def assess_version_churn(from_label: str, to_label: str, churn: Magnitude) -> Verdict:
    """Cross-check the bump declared by ``from_label`` -> ``to_label`` against ``churn``.

    Thin orchestrator: ``verdict_for(classify_bump(from_label, to_label), churn)``. Returns
    INAPPLICABLE for branch/non-semver references (no version to check) — consistent with DS5's
    by-RefKind degradation, where the cross-check simply does not apply.
    """
    return verdict_for(classify_bump(from_label, to_label), churn)
