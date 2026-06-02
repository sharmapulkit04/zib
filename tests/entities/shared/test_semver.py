"""Semver tests — pure leaf, so this is exhaustive.

Covers: parse (with/without leading 'v'; build-metadata + junk -> None);
ordering incl. prerelease precedence and is_stable; the full range subset
(exact, caret incl. 0.x / 0.0.z, tilde, x-range, '*'); the prerelease
EXCLUSION rule; and highest_satisfying selection / no-match.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.semver import (
    Range,
    Version,
    highest_satisfying,
)

V = Version.parse


# --- parse -----------------------------------------------------------------

@pytest.mark.parametrize(
    "text,expected",
    [
        ("1.2.3", Version(1, 2, 3)),
        ("v2.1.4", Version(2, 1, 4)),  # leading v stripped
        ("0.0.0", Version(0, 0, 0)),
        ("10.20.30", Version(10, 20, 30)),
        ("  1.2.3  ", Version(1, 2, 3)),  # surrounding whitespace tolerated
        ("1.0.0-alpha", Version(1, 0, 0, ("alpha",))),
        ("1.0.0-beta.2", Version(1, 0, 0, ("beta", 2))),
        ("v1.0.0-rc.1", Version(1, 0, 0, ("rc", 1))),
    ],
)
def test_parse_valid(text, expected):
    assert Version.parse(text) == expected


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "1",
        "1.2",
        "1.2.3.4",
        "1.2.x",
        "01.2.3",          # leading zero in core
        "1.2.3+build",     # build metadata unsupported
        "1.2.3-",          # empty prerelease
        "v",
        "abc",
        "=1.2.3",
        "1.2.-3",
    ],
)
def test_parse_invalid_returns_none(bad):
    assert Version.parse(bad) is None


def test_parse_non_string_returns_none():
    assert Version.parse(None) is None  # type: ignore[arg-type]


def test_str_roundtrip():
    assert str(V("1.2.3")) == "1.2.3"
    assert str(V("v1.2.3")) == "1.2.3"   # canonical form drops the 'v'
    assert str(V("1.0.0-beta.2")) == "1.0.0-beta.2"


# --- ordering & is_stable --------------------------------------------------

def test_core_ordering():
    assert V("1.0.0") < V("2.0.0")
    assert V("1.2.0") < V("1.10.0")   # numeric, not lexical
    assert V("1.2.3") < V("1.2.4")
    assert V("2.0.0") > V("1.99.99")


def test_prerelease_lower_than_release():
    assert V("1.0.0-alpha") < V("1.0.0")
    assert V("1.0.0") > V("1.0.0-rc.1")


def test_prerelease_precedence_chain():
    # SemVer §11.4 example chain.
    assert V("1.0.0-alpha") < V("1.0.0-alpha.1")
    assert V("1.0.0-alpha.1") < V("1.0.0-alpha.beta")
    assert V("1.0.0-alpha.beta") < V("1.0.0-beta")
    assert V("1.0.0-beta") < V("1.0.0-beta.2")
    assert V("1.0.0-beta.2") < V("1.0.0-beta.11")   # numeric ident compares numerically
    assert V("1.0.0-beta.11") < V("1.0.0-rc.1")


def test_numeric_below_alphanumeric_identifier():
    assert V("1.0.0-1") < V("1.0.0-alpha")


def test_equality_and_hash():
    assert V("1.2.3") == V("v1.2.3")
    assert hash(V("1.2.3")) == hash(V("1.2.3"))
    assert V("1.0.0-alpha") != V("1.0.0-beta")
    assert len({V("1.2.3"), V("v1.2.3")}) == 1


def test_is_stable():
    assert V("1.2.3").is_stable is True
    assert V("1.0.0-rc.1").is_stable is False


def test_sorting_mixed_list():
    versions = [V("1.0.0"), V("1.0.0-rc.1"), V("0.9.0"), V("1.0.0-alpha"), V("2.0.0")]
    ordered = sorted(versions)
    assert [str(v) for v in ordered] == [
        "0.9.0",
        "1.0.0-alpha",
        "1.0.0-rc.1",
        "1.0.0",
        "2.0.0",
    ]


# --- exact -----------------------------------------------------------------

def test_exact_matches_only_itself():
    rng = Range.from_spec("1.2.3")
    assert rng.satisfies(V("1.2.3")) is True
    assert rng.satisfies(V("1.2.4")) is False
    assert rng.satisfies(V("1.2.2")) is False
    assert rng.satisfies(V("2.0.0")) is False


# --- caret: normal ---------------------------------------------------------

def test_caret_normal_window():
    rng = Range.from_spec("^1.2.3")   # >=1.2.3 <2.0.0
    assert rng.satisfies(V("1.2.3")) is True
    assert rng.satisfies(V("1.2.4")) is True
    assert rng.satisfies(V("1.9.0")) is True
    assert rng.satisfies(V("2.0.0")) is False
    assert rng.satisfies(V("1.2.2")) is False
    assert rng.satisfies(V("1.0.0")) is False


def test_caret_excludes_prerelease_above_floor():
    # The headline exclusion case: ^1.2.3 must NOT match 2.0.0-rc.1.
    rng = Range.from_spec("^1.2.3")
    assert rng.satisfies(V("2.0.0-rc.1")) is False
    assert rng.satisfies(V("1.5.0-beta")) is False


# --- caret: 0.x special cases ---------------------------------------------

def test_caret_zero_minor():
    rng = Range.from_spec("^0.2.3")   # >=0.2.3 <0.3.0
    assert rng.satisfies(V("0.2.3")) is True
    assert rng.satisfies(V("0.2.9")) is True
    assert rng.satisfies(V("0.3.0")) is False
    assert rng.satisfies(V("0.2.2")) is False


def test_caret_zero_minor_zero_patch():
    rng = Range.from_spec("^0.0.3")   # >=0.0.3 <0.0.4
    assert rng.satisfies(V("0.0.3")) is True
    assert rng.satisfies(V("0.0.4")) is False
    assert rng.satisfies(V("0.1.0")) is False


# --- tilde -----------------------------------------------------------------

def test_tilde_full():
    rng = Range.from_spec("~1.2.3")   # >=1.2.3 <1.3.0
    assert rng.satisfies(V("1.2.3")) is True
    assert rng.satisfies(V("1.2.9")) is True
    assert rng.satisfies(V("1.3.0")) is False
    assert rng.satisfies(V("1.2.2")) is False


def test_tilde_minor_only():
    rng = Range.from_spec("~1.2")     # >=1.2.0 <1.3.0
    assert rng.satisfies(V("1.2.0")) is True
    assert rng.satisfies(V("1.2.5")) is True
    assert rng.satisfies(V("1.3.0")) is False


def test_tilde_major_only():
    rng = Range.from_spec("~1")       # >=1.0.0 <2.0.0
    assert rng.satisfies(V("1.0.0")) is True
    assert rng.satisfies(V("1.9.9")) is True
    assert rng.satisfies(V("2.0.0")) is False
    assert rng.satisfies(V("0.9.0")) is False


# --- x-range & wildcard ----------------------------------------------------

def test_x_range_patch():
    rng = Range.from_spec("1.2.x")    # >=1.2.0 <1.3.0
    assert rng.satisfies(V("1.2.0")) is True
    assert rng.satisfies(V("1.2.7")) is True
    assert rng.satisfies(V("1.3.0")) is False
    assert rng.satisfies(V("1.1.9")) is False


def test_x_range_minor():
    rng = Range.from_spec("1.x")      # >=1.0.0 <2.0.0
    assert rng.satisfies(V("1.0.0")) is True
    assert rng.satisfies(V("1.99.0")) is True
    assert rng.satisfies(V("2.0.0")) is False
    assert rng.satisfies(V("0.9.0")) is False


@pytest.mark.parametrize("spec", ["*", "x", "X"])
def test_full_wildcard_matches_any_stable(spec):
    rng = Range.from_spec(spec)
    assert rng.satisfies(V("0.0.1")) is True
    assert rng.satisfies(V("99.99.99")) is True
    # Wildcard does not name a prerelease, so prereleases are excluded.
    assert rng.satisfies(V("1.0.0-rc.1")) is False


# --- prerelease-naming ranges ----------------------------------------------

def test_caret_naming_prerelease_admits_same_core_prereleases():
    rng = Range.from_spec("^1.2.3-rc.1")
    assert rng.satisfies(V("1.2.3-rc.1")) is True
    assert rng.satisfies(V("1.2.3-rc.2")) is True
    assert rng.satisfies(V("1.2.3")) is True           # release of the floor core
    assert rng.satisfies(V("1.5.0-beta")) is False     # different core prerelease excluded
    assert rng.satisfies(V("1.9.0")) is True           # stable in window still ok


def test_exact_prerelease_matches_only_itself():
    rng = Range.from_spec("1.0.0-beta.2")
    assert rng.satisfies(V("1.0.0-beta.2")) is True
    assert rng.satisfies(V("1.0.0-beta.3")) is False
    assert rng.satisfies(V("1.0.0")) is False


# --- bad ranges ------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", ">=1.2.3", "^abc", "~", "1.2.3.4", "^"])
def test_unsupported_range_raises(bad):
    with pytest.raises(ValueError):
        Range.from_spec(bad)


# --- highest_satisfying ----------------------------------------------------

def test_highest_satisfying_picks_max_in_window():
    versions = [V("1.2.3"), V("1.4.0"), V("1.9.9"), V("2.0.0"), V("1.0.0")]
    rng = Range.from_spec("^1.2.3")
    assert highest_satisfying(versions, rng) == V("1.9.9")


def test_highest_satisfying_ignores_prereleases_for_stable_range():
    versions = [V("1.2.3"), V("2.0.0-rc.1"), V("1.5.0")]
    rng = Range.from_spec("^1.2.3")
    assert highest_satisfying(versions, rng) == V("1.5.0")


def test_highest_satisfying_none_when_no_match():
    versions = [V("1.0.0"), V("1.1.0")]
    rng = Range.from_spec("^2.0.0")
    assert highest_satisfying(versions, rng) is None


def test_highest_satisfying_empty_input():
    assert highest_satisfying([], Range.from_spec("*")) is None


def test_highest_satisfying_exact():
    versions = [V("1.2.3"), V("1.2.4"), V("1.2.3")]
    rng = Range.from_spec("1.2.3")
    assert highest_satisfying(versions, rng) == V("1.2.3")
