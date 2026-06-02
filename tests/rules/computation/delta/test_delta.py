"""Exhaustive unit tests for the magnitude classification rule (§9.2).

churn = (insertions + deletions) / max(lines_before, 1)
REWRITE iff churn >= threshold (default 0.5) else INCREMENTAL.
Concrete values only — each assertion pins an exact Magnitude.
"""

from zib.core.rules.computation.delta.delta import (
    DiffStats,
    Magnitude,
    classify_magnitude,
)


def test_zero_change_is_incremental():
    # No insertions, no deletions -> churn 0.0 -> INCREMENTAL.
    stats = DiffStats(files_changed=0, insertions=0, deletions=0, lines_before=400)
    assert classify_magnitude(stats) == Magnitude.INCREMENTAL


def test_small_change_under_threshold_is_incremental():
    # (10 + 5) / 400 = 0.0375 < 0.5 -> INCREMENTAL.
    stats = DiffStats(files_changed=2, insertions=10, deletions=5, lines_before=400)
    assert classify_magnitude(stats) == Magnitude.INCREMENTAL


def test_just_under_threshold_is_incremental():
    # (100 + 99) / 400 = 0.4975 < 0.5 -> INCREMENTAL (boundary, below).
    stats = DiffStats(files_changed=3, insertions=100, deletions=99, lines_before=400)
    assert classify_magnitude(stats) == Magnitude.INCREMENTAL


def test_at_threshold_exactly_is_rewrite():
    # (100 + 100) / 400 = 0.5 == 0.5 -> REWRITE (inclusive boundary).
    stats = DiffStats(files_changed=3, insertions=100, deletions=100, lines_before=400)
    assert classify_magnitude(stats) == Magnitude.REWRITE


def test_above_threshold_is_rewrite():
    # (250 + 50) / 400 = 0.75 >= 0.5 -> REWRITE.
    stats = DiffStats(files_changed=5, insertions=250, deletions=50, lines_before=400)
    assert classify_magnitude(stats) == Magnitude.REWRITE


def test_full_rewrite_deletions_equal_lines_before_is_rewrite():
    # Every prior line deleted plus a large fresh body:
    # (300 + 200) / 200 = 2.5 >= 0.5 -> REWRITE.
    stats = DiffStats(files_changed=4, insertions=300, deletions=200, lines_before=200)
    assert classify_magnitude(stats) == Magnitude.REWRITE


def test_empty_baseline_with_insertions_is_rewrite():
    # lines_before=0 -> denominator max(0,1)=1; (50 + 0)/1 = 50.0 -> REWRITE.
    stats = DiffStats(files_changed=1, insertions=50, deletions=0, lines_before=0)
    assert classify_magnitude(stats) == Magnitude.REWRITE


def test_empty_baseline_with_no_change_is_incremental():
    # lines_before=0 and zero churn -> 0/1 = 0.0 -> INCREMENTAL.
    stats = DiffStats(files_changed=0, insertions=0, deletions=0, lines_before=0)
    assert classify_magnitude(stats) == Magnitude.INCREMENTAL


def test_custom_threshold_lower_flips_to_rewrite():
    # (10 + 5) / 400 = 0.0375; with threshold 0.03 -> 0.0375 >= 0.03 -> REWRITE.
    stats = DiffStats(files_changed=2, insertions=10, deletions=5, lines_before=400)
    assert classify_magnitude(stats, threshold=0.03) == Magnitude.REWRITE


def test_custom_threshold_higher_stays_incremental():
    # (250 + 50) / 400 = 0.75; with threshold 0.8 -> 0.75 < 0.8 -> INCREMENTAL.
    stats = DiffStats(files_changed=5, insertions=250, deletions=50, lines_before=400)
    assert classify_magnitude(stats, threshold=0.8) == Magnitude.INCREMENTAL


def test_custom_threshold_inclusive_boundary_is_rewrite():
    # (60 + 40) / 400 = 0.25; with threshold 0.25 exactly -> REWRITE (>=).
    stats = DiffStats(files_changed=3, insertions=60, deletions=40, lines_before=400)
    assert classify_magnitude(stats, threshold=0.25) == Magnitude.REWRITE


def test_diffstats_is_frozen():
    # Contract: DiffStats is an immutable value object.
    stats = DiffStats(files_changed=1, insertions=1, deletions=1, lines_before=1)
    try:
        stats.insertions = 99  # type: ignore[misc]
    except Exception as exc:
        assert exc.__class__.__name__ == "FrozenInstanceError"
    else:
        raise AssertionError("DiffStats should be frozen")
