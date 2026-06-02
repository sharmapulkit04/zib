"""Value object tests — guards live at the type boundary, so they're tested here.

Exhaustive on construction validity and the manifest's mutually-exclusive ref-key rule.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
    RefSpec,
    Role,
)

SHA40 = "4f3a9c2e" + "0" * 32          # 40 hex
HASH64 = "sha256:" + "a" * 64


# --- RefName ---------------------------------------------------------------

@pytest.mark.parametrize("name", ["openspec", "a", "json-mapping", "otlp-1"])
def test_ref_name_accepts_valid(name):
    assert str(RefName(name)) == name


@pytest.mark.parametrize("name", ["", "-leading", "Upper", "has_underscore", "has space", "1starts"])
def test_ref_name_rejects_invalid(name):
    with pytest.raises(ValueError):
        RefName(name)


# --- Role ------------------------------------------------------------------

def test_role_accepts_label():
    assert str(Role("json-mapping")) == "json-mapping"


@pytest.mark.parametrize("role", ["", " padded ", "two\nlines"])
def test_role_rejects_invalid(role):
    with pytest.raises(ValueError):
        Role(role)


# --- CommitSha -------------------------------------------------------------

def test_commit_sha_accepts_40_hex_and_shortens():
    sha = CommitSha(SHA40)
    assert str(sha) == SHA40
    assert sha.short() == SHA40[:7]


@pytest.mark.parametrize("bad", ["", "abc", "g" * 40, "A" * 40, "0" * 39, "0" * 41])
def test_commit_sha_rejects_non_40_hex(bad):
    with pytest.raises(ValueError):
        CommitSha(bad)


# --- ContentHash -----------------------------------------------------------

def test_content_hash_accepts_canonical_form():
    assert str(ContentHash(HASH64)) == HASH64


@pytest.mark.parametrize("bad", ["a" * 64, "sha256:" + "a" * 63, "md5:" + "a" * 64, "sha256:XYZ"])
def test_content_hash_rejects_malformed(bad):
    with pytest.raises(ValueError):
        ContentHash(bad)


# --- RefSpec.from_manifest -------------------------------------------------

def test_ref_spec_version_range_is_semver():
    spec = RefSpec.from_manifest(version="^2.1.0")
    assert spec.kind is RefKind.SEMVER
    assert spec.value == "^2.1.0"


def test_ref_spec_exact_version_is_semver():
    assert RefSpec.from_manifest(version="2.1.4").kind is RefKind.SEMVER


def test_ref_spec_latest():
    spec = RefSpec.from_manifest(version="latest")
    assert spec.kind is RefKind.LATEST
    assert spec.value is None


def test_ref_spec_branch_tag_rev():
    assert RefSpec.from_manifest(branch="main").kind is RefKind.BRANCH
    assert RefSpec.from_manifest(tag="v2.1.0").kind is RefKind.TAG
    assert RefSpec.from_manifest(rev=SHA40).kind is RefKind.REV


def test_ref_spec_rev_must_be_full_sha():
    with pytest.raises(ValueError):
        RefSpec.from_manifest(rev="abc123")


def test_ref_spec_requires_exactly_one_key():
    with pytest.raises(ValueError):
        RefSpec.from_manifest()  # none
    with pytest.raises(ValueError):
        RefSpec.from_manifest(version="^1.0.0", branch="main")  # two


def test_ref_spec_latest_takes_no_value_directly():
    with pytest.raises(ValueError):
        RefSpec(RefKind.LATEST, "something")
