"""Tests for resolve_version + its highest_satisfying_tag sub-rule.

Concrete-value assertions throughout: every test pins the exact tag name (and
commit) the resolver must return, so a behavior change breaks a specific value.
"""

from __future__ import annotations

import hashlib

import pytest

from zib.core.entities.shared.semver import Range
from zib.core.entities.shared.value_objects import CommitSha, RefKind, RefSpec
from zib.core.gateways.git.port.git_port import GitTag
from zib.core.rules.computation.version_resolution.highest_tag import (
    highest_satisfying_tag,
)
from zib.core.rules.computation.version_resolution.version_resolution import (
    resolve_version,
)


def _sha(seed: str) -> CommitSha:
    # Deterministic, valid 40-hex sha derived from the tag name.
    return CommitSha(hashlib.sha1(seed.encode()).hexdigest())


def _tag(name: str, seed: str | None = None) -> GitTag:
    return GitTag(name=name, commit=_sha(seed or name))


# --------------------------------------------------------------------------- #
# highest_satisfying_tag — exhaustive sub-rule tests
# --------------------------------------------------------------------------- #


def test_highest_tag_picks_greatest_among_several():
    tags = [_tag("1.0.0"), _tag("2.1.4"), _tag("2.0.0"), _tag("1.9.9")]
    rng = Range.from_spec("^1.0.0")
    result = highest_satisfying_tag(tags, rng)
    assert result is not None
    assert result.name == "1.9.9"


def test_highest_tag_caret_excludes_next_major():
    tags = [_tag("2.1.4"), _tag("2.9.0"), _tag("3.0.0")]
    rng = Range.from_spec("^2.1.0")
    assert highest_satisfying_tag(tags, rng).name == "2.9.0"


def test_highest_tag_v_prefix_parsed():
    tags = [_tag("v2.1.0"), _tag("v2.3.1"), _tag("v1.0.0")]
    rng = Range.from_spec("^2.0.0")
    assert highest_satisfying_tag(tags, rng).name == "v2.3.1"


def test_highest_tag_ignores_non_semver_names():
    tags = [_tag("release-candidate"), _tag("nightly"), _tag("1.4.0")]
    rng = Range.from_spec("^1.0.0")
    result = highest_satisfying_tag(tags, rng)
    assert result is not None and result.name == "1.4.0"


def test_highest_tag_excludes_prereleases_for_stable_range():
    tags = [_tag("2.0.0-rc.1"), _tag("1.9.0"), _tag("2.0.0-beta.2")]
    rng = Range.from_spec("^1.0.0")
    assert highest_satisfying_tag(tags, rng).name == "1.9.0"


def test_highest_tag_returns_none_when_nothing_satisfies():
    tags = [_tag("1.0.0"), _tag("1.5.0")]
    rng = Range.from_spec("^2.0.0")
    assert highest_satisfying_tag(tags, rng) is None


def test_highest_tag_returns_none_with_no_parseable_tags():
    tags = [_tag("stable"), _tag("edge")]
    assert highest_satisfying_tag(tags, Range.from_spec("*")) is None


def test_highest_tag_exact_range_matches_single_version():
    tags = [_tag("2.1.3"), _tag("2.1.4"), _tag("2.1.5")]
    rng = Range.from_spec("2.1.4")
    result = highest_satisfying_tag(tags, rng)
    assert result is not None and result.name == "2.1.4"


# --------------------------------------------------------------------------- #
# resolve_version — SEMVER lane
# --------------------------------------------------------------------------- #


def test_semver_range_picks_highest_in_range():
    spec = RefSpec(RefKind.SEMVER, "^2.1.0")
    tags = [_tag("2.1.0"), _tag("2.4.2"), _tag("2.2.0"), _tag("3.0.0")]
    result = resolve_version(spec, tags)
    assert result.name == "2.4.2"


def test_semver_exact_pin_returns_that_tag():
    spec = RefSpec(RefKind.SEMVER, "2.1.4")
    tags = [_tag("2.1.3"), _tag("2.1.4"), _tag("2.1.5"), _tag("3.0.0")]
    result = resolve_version(spec, tags)
    assert result.name == "2.1.4"


def test_semver_v_prefixed_tags_resolve():
    spec = RefSpec(RefKind.SEMVER, "~1.2.0")
    tags = [_tag("v1.2.0"), _tag("v1.2.7"), _tag("v1.3.0")]
    result = resolve_version(spec, tags)
    assert result.name == "v1.2.7"


def test_semver_no_satisfying_tag_raises_naming_constraint():
    spec = RefSpec(RefKind.SEMVER, "^9.0.0")
    tags = [_tag("1.0.0"), _tag("2.0.0")]
    with pytest.raises(ValueError) as exc:
        resolve_version(spec, tags)
    assert "^9.0.0" in str(exc.value)


def test_semver_non_semver_tags_are_unresolvable():
    spec = RefSpec(RefKind.SEMVER, "^1.0.0")
    tags = [_tag("stable"), _tag("nightly")]
    with pytest.raises(ValueError) as exc:
        resolve_version(spec, tags)
    assert "^1.0.0" in str(exc.value)


# --------------------------------------------------------------------------- #
# resolve_version — LATEST lane
# --------------------------------------------------------------------------- #


def test_latest_picks_highest_stable_version():
    spec = RefSpec(RefKind.LATEST, None)
    tags = [_tag("1.0.0"), _tag("2.3.0"), _tag("2.0.0")]
    result = resolve_version(spec, tags)
    assert result.name == "2.3.0"


def test_latest_excludes_prereleases():
    spec = RefSpec(RefKind.LATEST, None)
    tags = [_tag("2.0.0"), _tag("3.0.0-rc.1"), _tag("3.0.0-beta.5")]
    result = resolve_version(spec, tags)
    assert result.name == "2.0.0"


def test_latest_with_no_stable_tags_raises():
    spec = RefSpec(RefKind.LATEST, None)
    tags = [_tag("1.0.0-rc.1"), _tag("nightly")]
    with pytest.raises(ValueError) as exc:
        resolve_version(spec, tags)
    assert "latest" in str(exc.value)


# --------------------------------------------------------------------------- #
# resolve_version — TAG lane (literal, no semver)
# --------------------------------------------------------------------------- #


def test_tag_literal_exact_match():
    spec = RefSpec(RefKind.TAG, "release-2024")
    tags = [_tag("release-2024"), _tag("2.0.0")]
    result = resolve_version(spec, tags)
    assert result.name == "release-2024"


def test_tag_literal_does_not_semver_interpret():
    # 'v2' is not a full semver; literal TAG must still find it by exact name.
    spec = RefSpec(RefKind.TAG, "v2")
    tags = [_tag("v2"), _tag("2.0.0")]
    result = resolve_version(spec, tags)
    assert result.name == "v2"


def test_tag_missing_raises():
    spec = RefSpec(RefKind.TAG, "v9.9.9")
    tags = [_tag("v1.0.0")]
    with pytest.raises(ValueError) as exc:
        resolve_version(spec, tags)
    assert "v9.9.9" in str(exc.value)


# --------------------------------------------------------------------------- #
# resolve_version — guard: commit-level kinds rejected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind,value", [(RefKind.BRANCH, "main"), (RefKind.REV, "a" * 40)])
def test_branch_and_rev_kinds_rejected(kind, value):
    spec = RefSpec(kind, value)
    with pytest.raises(ValueError) as exc:
        resolve_version(spec, [_tag("1.0.0")])
    assert kind.value in str(exc.value)
