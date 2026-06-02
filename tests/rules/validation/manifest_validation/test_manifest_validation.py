"""Exhaustive tests for the manifest reference boundary validator.

A leaf validation rule: pure input -> list of violation strings. Every case asserts
concrete behavior — the exact emptiness/length of the list and the specific phrase that
identifies which check fired — so a regression in any single check is unambiguous.
"""

from __future__ import annotations

from zib.core.rules.validation.manifest_validation.manifest_validation import (
    validate_reference,
)


def test_fully_valid_reference_has_no_violations():
    violations = validate_reference(
        name="json-mapping",
        role="json-mapping",
        source="openspec/openspec",
        version="^2.1.0",
        subdirectory="specification/core",
    )
    assert violations == []


def test_valid_with_each_single_ref_lane():
    assert validate_reference(name="a", role="r", source="o/r", version="latest") == []
    assert validate_reference(name="a", role="r", source="o/r", branch="main") == []
    assert validate_reference(name="a", role="r", source="o/r", tag="v1.2.3") == []
    assert (
        validate_reference(
            name="a", role="r", source="o/r", rev="a" * 40
        )
        == []
    )


def test_valid_source_forms_all_accepted():
    for src in (
        "owner/repo",
        "https://github.com/owner/repo",
        "http://example.com/x.git",
        "git://host/owner/repo",
        "ssh://git@host/owner/repo",
        "git@github.com:owner/repo.git",
        "/abs/path/to/repo",
        "~/repos/thing",
        "./local/repo",
        "../sibling/repo",
        "some/local/repo.git",
    ):
        assert (
            validate_reference(name="a", role="r", source=src, version="1.0.0") == []
        ), src


def test_invalid_name_uppercase():
    violations = validate_reference(
        name="Json-Mapping", role="r", source="o/r", version="1.0.0"
    )
    assert len(violations) == 1
    assert "invalid name" in violations[0]


def test_invalid_name_leading_digit():
    violations = validate_reference(
        name="1abc", role="r", source="o/r", version="1.0.0"
    )
    assert len(violations) == 1
    assert "invalid name" in violations[0]


def test_invalid_role_empty_and_multiline():
    empty = validate_reference(name="a", role="", source="o/r", version="1.0.0")
    assert len(empty) == 1
    assert "invalid role" in empty[0]

    multiline = validate_reference(
        name="a", role="line1\nline2", source="o/r", version="1.0.0"
    )
    assert len(multiline) == 1
    assert "invalid role" in multiline[0]


def test_role_with_surrounding_whitespace_rejected():
    violations = validate_reference(
        name="a", role=" padded ", source="o/r", version="1.0.0"
    )
    assert len(violations) == 1
    assert "invalid role" in violations[0]


def test_missing_source():
    violations = validate_reference(name="a", role="r", source="", version="1.0.0")
    assert len(violations) == 1
    assert "missing source" in violations[0]


def test_implausible_source():
    violations = validate_reference(
        name="a", role="r", source="not a source!", version="1.0.0"
    )
    assert len(violations) == 1
    assert "invalid source" in violations[0]


def test_no_ref_specified():
    violations = validate_reference(name="a", role="r", source="o/r")
    assert len(violations) == 1
    assert "no ref specified" in violations[0]


def test_too_many_refs_specified():
    violations = validate_reference(
        name="a", role="r", source="o/r", version="1.0.0", branch="main"
    )
    assert len(violations) == 1
    assert "ambiguous ref" in violations[0]
    assert "branch" in violations[0] and "version" in violations[0]


def test_invalid_rev_not_40_hex():
    short = validate_reference(name="a", role="r", source="o/r", rev="abc123")
    assert len(short) == 1
    assert "invalid rev" in short[0]

    nonhex = validate_reference(name="a", role="r", source="o/r", rev="g" * 40)
    assert len(nonhex) == 1
    assert "invalid rev" in nonhex[0]


def test_subdirectory_absolute_rejected():
    violations = validate_reference(
        name="a", role="r", source="o/r", version="1.0.0", subdirectory="/etc/passwd"
    )
    assert len(violations) == 1
    assert "invalid subdirectory" in violations[0]
    assert "absolute" in violations[0]


def test_subdirectory_traversal_rejected():
    violations = validate_reference(
        name="a", role="r", source="o/r", version="1.0.0", subdirectory="spec/../../x"
    )
    assert len(violations) == 1
    assert "invalid subdirectory" in violations[0]
    assert "'..'" in violations[0]


def test_subdirectory_with_dotdot_filename_is_allowed():
    # '..foo' is a normal segment, not a traversal — only the exact '..' segment is bad.
    violations = validate_reference(
        name="a", role="r", source="o/r", version="1.0.0", subdirectory="spec/..foo"
    )
    assert violations == []


def test_multiple_violations_accumulate():
    violations = validate_reference(
        name="BadName",
        role="",
        source="!!!",
        version="1.0.0",
        branch="main",
        rev="xyz",
        subdirectory="/abs/../bad",
    )
    # name, role, source, ambiguous-ref, rev, subdir-absolute, subdir-traversal = 7
    assert len(violations) == 7
    joined = "\n".join(violations)
    assert "invalid name" in joined
    assert "invalid role" in joined
    assert "invalid source" in joined
    assert "ambiguous ref" in joined
    assert "invalid rev" in joined
    assert "absolute" in joined
    assert "'..'" in joined
