"""FetchProcess tests — outbound git fetch lifecycle against the FakeGitPort.

Proves the process exports the registered tree, pins it with the real content_hash rule
(not a re-implementation), and forwards the subdirectory scope to the port. Each assertion
is a concrete value, not a shape.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.fetch.translator.fetch_types import FetchedRef
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash
from tests.gateways.git.port.fake_git_port import FakeGitPort

SOURCE = "github.com/acme/specs"
COMMIT_HEX = "a" * 40
OTHER_HEX = "b" * 40

REG = TreeEntry(path="README.md", mode=0o100644, blob=b"# spec\n")
EXEC = TreeEntry(path="run.sh", mode=0o100755, blob=b"#!/bin/sh\necho hi\n")


def _process_with_tree(entries: list[TreeEntry]) -> tuple[FetchProcess, FakeGitPort]:
    port = FakeGitPort()
    port.set_tree(SOURCE, COMMIT_HEX, entries)
    return FetchProcess(port), port


def test_returns_fetchedref_with_exact_tree() -> None:
    process, _ = _process_with_tree([REG, EXEC])

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)

    assert isinstance(result, FetchedRef)
    assert result.tree == [REG, EXEC]
    assert len(result.tree) == 2


def test_content_hash_matches_real_rule() -> None:
    entries = [REG, EXEC]
    process, _ = _process_with_tree(entries)

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)

    assert result.content_hash == compute_content_hash(entries)


def test_content_hash_has_canonical_prefix() -> None:
    process, _ = _process_with_tree([REG])

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)

    assert result.content_hash.value.startswith("sha256:")
    assert len(result.content_hash.value) == len("sha256:") + 64


def test_single_file_tree() -> None:
    process, _ = _process_with_tree([REG])

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)

    assert result.tree == [REG]
    assert result.content_hash == compute_content_hash([REG])


def test_empty_tree_hashes_to_empty_sha256() -> None:
    process, _ = _process_with_tree([])

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)

    assert result.tree == []
    # SHA-256 of the empty byte stream.
    assert result.content_hash.value == (
        "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_subdirectory_forwarded_to_port() -> None:
    nested_a = TreeEntry(path="docs/a.md", mode=0o100644, blob=b"a\n")
    nested_b = TreeEntry(path="docs/b.md", mode=0o100644, blob=b"b\n")
    process, _ = _process_with_tree([REG, nested_a, nested_b])

    result = process.fetch(SOURCE, CommitSha(COMMIT_HEX), "docs")

    # FakeGitPort scopes export_tree to the subdirectory prefix; the top-level
    # README must be excluded, proving the subdirectory argument was forwarded.
    assert result.tree == [nested_a, nested_b]
    assert result.content_hash == compute_content_hash([nested_a, nested_b])


def test_subdirectory_scope_changes_content_hash() -> None:
    nested = TreeEntry(path="docs/a.md", mode=0o100644, blob=b"a\n")
    process, _ = _process_with_tree([REG, nested])

    full = process.fetch(SOURCE, CommitSha(COMMIT_HEX), None)
    scoped = process.fetch(SOURCE, CommitSha(COMMIT_HEX), "docs")

    assert full.tree == [REG, nested]
    assert scoped.tree == [nested]
    assert full.content_hash != scoped.content_hash


def test_unknown_commit_raises_keyerror() -> None:
    process, _ = _process_with_tree([REG])

    with pytest.raises(KeyError):
        process.fetch(SOURCE, CommitSha(OTHER_HEX), None)
