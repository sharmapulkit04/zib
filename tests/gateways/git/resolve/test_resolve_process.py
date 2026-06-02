"""ResolveProcess lifecycle tests — one process, five ref kinds, concrete asserts.

Drives the process through the validated :class:`FakeGitPort`. Each test pins an
exact commit SHA, label, and ref_type so a behavior change breaks loudly.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.value_objects import CommitSha, RefKind, RefSpec
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.gateways.git.resolve.translator.resolve_types import ResolvedRef
from tests.gateways.git.port.fake_git_port import FakeGitPort

SOURCE = "github.com/acme/spec"

# Distinct, well-formed 40-hex commit SHAs.
C_120 = "a" * 40
C_130 = "b" * 40
C_140 = "c" * 40
C_200 = "d" * 40
C_MAIN = "e" * 40
C_REV = "f" * 40
C_PRE = "1" * 40


def _port_with_tags() -> FakeGitPort:
    port = FakeGitPort()
    port.add_tag(SOURCE, "1.2.0", C_120)
    port.add_tag(SOURCE, "1.3.0", C_130)
    port.add_tag(SOURCE, "1.4.0", C_140)
    port.add_tag(SOURCE, "2.0.0", C_200)
    return port


def test_semver_caret_picks_highest_in_range() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.SEMVER, "^1.2.0"))

    assert result == ResolvedRef(
        commit=CommitSha(C_140),
        label="1.4.0",
        ref_type=RefKind.SEMVER,
    )


def test_semver_exact_pin_selects_that_tag() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.SEMVER, "1.3.0"))

    assert result.commit.value == C_130
    assert result.label == "1.3.0"
    assert result.ref_type is RefKind.SEMVER


def test_semver_no_satisfying_tag_raises_valueerror() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    with pytest.raises(ValueError):
        process.resolve(SOURCE, RefSpec(RefKind.SEMVER, "^9.0.0"))


def test_latest_picks_newest_stable() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.LATEST, None))

    assert result.commit.value == C_200
    assert result.label == "2.0.0"
    assert result.ref_type is RefKind.LATEST


def test_latest_ignores_prerelease_tag() -> None:
    port = _port_with_tags()
    port.add_tag(SOURCE, "2.1.0-rc.1", C_PRE)  # newer but prerelease
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.LATEST, None))

    assert result.commit.value == C_200
    assert result.label == "2.0.0"
    assert result.ref_type is RefKind.LATEST


def test_tag_literal_taken_as_is() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.TAG, "1.3.0"))

    assert result.commit.value == C_130
    assert result.label == "1.3.0"
    assert result.ref_type is RefKind.TAG


def test_tag_literal_unknown_raises_valueerror() -> None:
    port = _port_with_tags()
    process = ResolveProcess(port)

    with pytest.raises(ValueError):
        process.resolve(SOURCE, RefSpec(RefKind.TAG, "nonexistent"))


def test_branch_resolves_to_tip_with_branch_label() -> None:
    port = FakeGitPort()
    port.set_branch(SOURCE, "main", C_MAIN)
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.BRANCH, "main"))

    assert result.commit.value == C_MAIN
    assert result.label == "main"
    assert result.ref_type is RefKind.BRANCH


def test_branch_unknown_raises_keyerror() -> None:
    port = FakeGitPort()
    process = ResolveProcess(port)

    with pytest.raises(KeyError):
        process.resolve(SOURCE, RefSpec(RefKind.BRANCH, "ghost"))


def test_rev_frozen_label_is_short_sha() -> None:
    port = FakeGitPort()
    port.add_rev(SOURCE, C_REV)
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.REV, C_REV))

    assert result.commit.value == C_REV
    assert result.label == "fffffff"  # short() == first 7 chars
    assert result.ref_type is RefKind.REV


def test_rev_label_is_seven_chars() -> None:
    port = FakeGitPort()
    port.add_rev(SOURCE, C_REV)
    process = ResolveProcess(port)

    result = process.resolve(SOURCE, RefSpec(RefKind.REV, C_REV))

    assert len(result.label) == 7
    assert result.commit.short() == result.label
