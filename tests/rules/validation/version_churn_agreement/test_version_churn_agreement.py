"""Exhaustive unit tests for the version-vs-churn cross-check (decisions.md DS5).

Three levels, per the architecture:
    classify_bump   — exhaustive: every SemVer bump level + non-semver + no-bump edges
    verdict_for     — exhaustive: the full (bump x churn) decision table
    assess_version_churn — narrow: proves the orchestrator wires the two together

Concrete values only — each assertion pins an exact BumpLevel / Verdict.
"""

from zib.core.rules.computation.delta.delta import Magnitude
from zib.core.rules.validation.version_churn_agreement.version_churn_agreement import (
    BumpLevel,
    Verdict,
    assess_version_churn,
    classify_bump,
    verdict_for,
)

# --------------------------------------------------------------------- classify_bump


def test_patch_bump():
    assert classify_bump("3.3.0", "3.3.1") == BumpLevel.PATCH


def test_minor_bump():
    assert classify_bump("3.3.0", "3.4.0") == BumpLevel.MINOR


def test_major_bump():
    assert classify_bump("3.3.0", "4.0.0") == BumpLevel.MAJOR


def test_major_bump_dominates_lower_components():
    # 3.9.5 -> 4.0.0: major increased, so MAJOR regardless of minor/patch dropping to 0.
    assert classify_bump("3.9.5", "4.0.0") == BumpLevel.MAJOR


def test_minor_bump_with_patch_reset():
    # 3.3.5 -> 3.4.0: minor increased (major equal); patch reset is irrelevant -> MINOR.
    assert classify_bump("3.3.5", "3.4.0") == BumpLevel.MINOR


def test_v_prefix_is_accepted():
    # The SemVer parser tolerates a leading 'v'.
    assert classify_bump("v3.3.0", "v3.4.0") == BumpLevel.MINOR


def test_same_version_is_none():
    assert classify_bump("3.3.0", "3.3.0") == BumpLevel.NONE


def test_minor_downgrade_is_none():
    assert classify_bump("3.4.0", "3.3.0") == BumpLevel.NONE


def test_major_downgrade_is_none():
    # 4.0.0 -> 3.9.9: no core component increased -> NONE (not a forward bump).
    assert classify_bump("4.0.0", "3.9.9") == BumpLevel.NONE


def test_prerelease_only_change_is_none():
    # Same core (3.3.0); only the prerelease differs -> no forward core bump.
    assert classify_bump("3.3.0-rc.1", "3.3.0") == BumpLevel.NONE


def test_non_semver_from_label_is_unknown():
    # A branch tip on the from-side: no version signal.
    assert classify_bump("main", "3.3.0") == BumpLevel.UNKNOWN


def test_non_semver_to_label_is_unknown():
    assert classify_bump("3.3.0", "feature-retries") == BumpLevel.UNKNOWN


def test_both_non_semver_is_unknown():
    assert classify_bump("main", "develop") == BumpLevel.UNKNOWN


# --------------------------------------------------------------------- verdict_for


def test_patch_incremental_is_consistent():
    assert verdict_for(BumpLevel.PATCH, Magnitude.INCREMENTAL) == Verdict.CONSISTENT


def test_patch_rewrite_is_under_promised():
    # The headline failure: tagged a patch, but the content was rewritten.
    assert verdict_for(BumpLevel.PATCH, Magnitude.REWRITE) == Verdict.UNDER_PROMISED


def test_minor_incremental_is_consistent():
    assert verdict_for(BumpLevel.MINOR, Magnitude.INCREMENTAL) == Verdict.CONSISTENT


def test_minor_rewrite_is_under_promised():
    assert verdict_for(BumpLevel.MINOR, Magnitude.REWRITE) == Verdict.UNDER_PROMISED


def test_major_rewrite_is_consistent():
    # MAJOR already warns of a large/breaking change -> a rewrite is expected, not a surprise.
    assert verdict_for(BumpLevel.MAJOR, Magnitude.REWRITE) == Verdict.CONSISTENT


def test_major_incremental_is_consistent():
    # Over-promise (small change tagged major) is harmless -> not flagged.
    assert verdict_for(BumpLevel.MAJOR, Magnitude.INCREMENTAL) == Verdict.CONSISTENT


def test_none_bump_is_inapplicable_regardless_of_churn():
    assert verdict_for(BumpLevel.NONE, Magnitude.INCREMENTAL) == Verdict.INAPPLICABLE
    assert verdict_for(BumpLevel.NONE, Magnitude.REWRITE) == Verdict.INAPPLICABLE


def test_unknown_bump_is_inapplicable_regardless_of_churn():
    # Branch / non-semver references: nothing to cross-check (DS5 degradation).
    assert verdict_for(BumpLevel.UNKNOWN, Magnitude.INCREMENTAL) == Verdict.INAPPLICABLE
    assert verdict_for(BumpLevel.UNKNOWN, Magnitude.REWRITE) == Verdict.INAPPLICABLE


# --------------------------------------------------------------------- assess_version_churn (orchestrator)


def test_orchestrator_flags_minor_rewrite():
    # 3.3.0 -> 3.4.0 (MINOR) + REWRITE -> the under-promise flag, end to end.
    assert assess_version_churn("3.3.0", "3.4.0", Magnitude.REWRITE) == Verdict.UNDER_PROMISED


def test_orchestrator_consistent_for_major_rewrite():
    assert assess_version_churn("3.3.0", "4.0.0", Magnitude.REWRITE) == Verdict.CONSISTENT


def test_orchestrator_inapplicable_for_branch():
    # A branch-tracked reference -> no version signal -> INAPPLICABLE.
    assert assess_version_churn("main", "main", Magnitude.REWRITE) == Verdict.INAPPLICABLE
