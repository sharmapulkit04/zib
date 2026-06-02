"""Exhaustive unit tests for the constraint-drift rule.

Pure function: (live spec, current resolved version, available tags) -> verdict.
Concrete assertions on both status and target string.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.value_objects import CommitSha, RefKind, RefSpec
from zib.core.gateways.git.port.git_port import GitTag
from zib.core.rules.validation.constraint_drift.constraint_drift import (
    DriftResult,
    DriftStatus,
    assess_drift,
)

_C = CommitSha("a" * 40)  # commit irrelevant to drift; reused everywhere.


def _tags(*names: str) -> list[GitTag]:
    return [GitTag(name=n, commit=_C) for n in names]


# ---- SEMVER: newer in-range version is an UPDATE -------------------------

def test_semver_update_within_caret_constraint():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    result = assess_drift(spec, "2.1.0", _tags("2.1.0", "2.1.4", "2.3.0"))
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "2.3.0")


def test_semver_update_picks_highest_in_range_not_the_first():
    spec = RefSpec(RefKind.SEMVER, "^1.2.0")
    result = assess_drift(spec, "1.2.0", _tags("1.2.1", "1.5.9", "1.9.0", "2.0.0"))
    # 2.0.0 is out of ^1 range; 1.9.0 is the highest in-range update.
    assert result.status is DriftStatus.UPDATE_AVAILABLE
    assert result.target == "1.9.0"


def test_semver_tilde_update_within_minor():
    spec = RefSpec(RefKind.SEMVER, "~1.2.3")
    result = assess_drift(spec, "1.2.3", _tags("1.2.3", "1.2.9", "1.3.0"))
    # ~1.2.3 -> >=1.2.3 <1.3.0 ; highest in-range is 1.2.9.
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "1.2.9")


def test_semver_leading_v_on_current_and_tags():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    result = assess_drift(spec, "v2.1.0", _tags("v2.1.0", "v2.2.0"))
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "2.2.0")


# ---- SEMVER: newer only out-of-range is an UPGRADE -----------------------

def test_semver_upgrade_new_major_outside_caret_range():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    result = assess_drift(spec, "2.1.0", _tags("2.1.0", "3.0.0"))
    # No in-range newer; 3.0.0 is beyond ^2 -> upgrade jumps to latest overall.
    assert result == DriftResult(DriftStatus.UPGRADE_AVAILABLE, "3.0.0")


def test_semver_upgrade_target_is_highest_overall_even_past_in_range():
    spec = RefSpec(RefKind.SEMVER, "~1.2.0")
    result = assess_drift(spec, "1.2.5", _tags("1.2.5", "2.0.0", "3.1.0"))
    # ~1.2.0 admits nothing newer than 1.2.5; upgrade target is the highest overall.
    assert result == DriftResult(DriftStatus.UPGRADE_AVAILABLE, "3.1.0")


def test_semver_in_range_update_wins_over_out_of_range_upgrade():
    spec = RefSpec(RefKind.SEMVER, "^2.0.0")
    result = assess_drift(spec, "2.0.0", _tags("2.4.0", "3.0.0"))
    # Both exist; in-range UPDATE is reported (not the out-of-range 3.0.0).
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "2.4.0")


# ---- SEMVER: nothing newer -> UP_TO_DATE ---------------------------------

def test_semver_up_to_date_when_current_is_highest():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    result = assess_drift(spec, "2.5.0", _tags("2.1.0", "2.3.0", "2.5.0"))
    assert result == DriftResult(DriftStatus.UP_TO_DATE, None)


def test_semver_up_to_date_when_only_older_tags_exist():
    spec = RefSpec(RefKind.SEMVER, "^1.0.0")
    result = assess_drift(spec, "1.4.0", _tags("1.0.0", "1.2.0", "1.4.0"))
    assert result == DriftResult(DriftStatus.UP_TO_DATE, None)


# ---- prerelease gate -----------------------------------------------------

def test_semver_ignores_prerelease_tags_for_stable_constraint():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    result = assess_drift(spec, "2.1.0", _tags("2.1.0", "2.2.0-rc.1", "3.0.0-beta.1"))
    # Both newer tags are prereleases; a stable ^range excludes them entirely.
    assert result == DriftResult(DriftStatus.UP_TO_DATE, None)


def test_semver_non_version_tags_are_ignored():
    spec = RefSpec(RefKind.SEMVER, "^1.0.0")
    result = assess_drift(spec, "1.0.0", _tags("1.0.0", "release-candidate", "nightly", "1.2.0"))
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "1.2.0")


# ---- LATEST lane ---------------------------------------------------------

def test_latest_update_when_newer_available():
    spec = RefSpec(RefKind.LATEST, None)
    result = assess_drift(spec, "2.1.0", _tags("2.1.0", "2.4.0", "3.0.0"))
    # latest tracks the highest stable version overall.
    assert result == DriftResult(DriftStatus.UPDATE_AVAILABLE, "3.0.0")


def test_latest_up_to_date_when_current_is_highest():
    spec = RefSpec(RefKind.LATEST, None)
    result = assess_drift(spec, "3.0.0", _tags("2.1.0", "2.4.0", "3.0.0"))
    assert result == DriftResult(DriftStatus.UP_TO_DATE, None)


def test_latest_ignores_prereleases_for_stable_pin():
    spec = RefSpec(RefKind.LATEST, None)
    result = assess_drift(spec, "2.0.0", _tags("2.0.0", "2.1.0-rc.1", "3.0.0-beta.2"))
    assert result == DriftResult(DriftStatus.UP_TO_DATE, None)


# ---- scope guard ---------------------------------------------------------

def test_rejects_non_resolving_ref_kinds():
    for kind, value in (
        (RefKind.TAG, "v1.2.3"),
        (RefKind.BRANCH, "main"),
        (RefKind.REV, "b" * 40),
    ):
        with pytest.raises(ValueError):
            assess_drift(RefSpec(kind, value), "1.2.3", _tags("2.0.0"))


def test_rejects_unparseable_current_version():
    spec = RefSpec(RefKind.SEMVER, "^1.0.0")
    with pytest.raises(ValueError):
        assess_drift(spec, "not-a-version", _tags("1.2.0"))
