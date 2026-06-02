"""GitPort contract test — the behavioral contract every GitPort implementation must satisfy.

CLAUDE.md invariant 6: a fake is only trusted in tests above once it passes the contract test
of the interface it implements. These tests pin down FakeGitPort against the documented
GitPort behavior; the real infrastructure adapter re-runs the same expectations against the
git CLI. Every assertion is concrete (exact commits, lists, booleans), so a behavior drift
breaks here, not three layers up.
"""

from __future__ import annotations

import pytest

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry
from zib.core.gateways.git.port.git_port import GitCommit, GitPort, GitTag
from tests.gateways.git.port.fake_git_port import FakeGitPort

SRC = "github.com/acme/specs"

C1 = "1" * 40
C2 = "2" * 40
C3 = "3" * 40


def _file(path: str, body: str) -> TreeEntry:
    return TreeEntry(path=path, mode=0o100644, blob=body.encode())


def test_fake_satisfies_git_port_protocol():
    port = FakeGitPort()
    assert isinstance(port, GitPort)


def test_list_tags_returns_registered_tags_in_order():
    port = FakeGitPort()
    port.add_tag(SRC, "v1.0.0", C1)
    port.add_tag(SRC, "v2.0.0", C2)
    tags = port.list_tags(SRC)
    assert tags == [
        GitTag("v1.0.0", CommitSha(C1)),
        GitTag("v2.0.0", CommitSha(C2)),
    ]


def test_list_tags_empty_for_unknown_source():
    assert FakeGitPort().list_tags("nope") == []


def test_resolve_branch_name_to_commit():
    port = FakeGitPort()
    port.set_branch(SRC, "main", C2)
    assert port.resolve(SRC, "main") == CommitSha(C2)


def test_resolve_tag_name_to_commit():
    port = FakeGitPort()
    port.add_tag(SRC, "v3.1.0", C3)
    assert port.resolve(SRC, "v3.1.0") == CommitSha(C3)


def test_resolve_registered_rev_returns_itself():
    port = FakeGitPort()
    port.add_rev(SRC, C1)
    assert port.resolve(SRC, C1) == CommitSha(C1)


def test_resolve_bare_40hex_sha_resolves_to_itself_even_if_unregistered():
    assert FakeGitPort().resolve(SRC, C2) == CommitSha(C2)


def test_resolve_unknown_name_raises_keyerror():
    with pytest.raises(KeyError):
        FakeGitPort().resolve(SRC, "does-not-exist")


def test_export_tree_returns_registered_tree():
    port = FakeGitPort()
    tree = [_file("README.md", "hi"), _file("spec.md", "body")]
    port.set_tree(SRC, C1, tree)
    assert port.export_tree(SRC, CommitSha(C1), None) == tree


def test_export_tree_unset_commit_raises():
    with pytest.raises(KeyError):
        FakeGitPort().export_tree(SRC, CommitSha(C1), None)


def test_export_tree_scopes_to_subdirectory():
    port = FakeGitPort()
    port.set_tree(
        SRC,
        C1,
        [_file("docs/a.md", "a"), _file("docs/b.md", "b"), _file("top.md", "t")],
    )
    scoped = port.export_tree(SRC, CommitSha(C1), "docs")
    assert [e.path for e in scoped] == ["docs/a.md", "docs/b.md"]


def test_diff_returns_registered_text():
    port = FakeGitPort()
    port.set_diff(SRC, C1, C2, "@@ -1 +1 @@\n-old\n+new\n")
    assert port.diff(SRC, CommitSha(C1), CommitSha(C2), None) == "@@ -1 +1 @@\n-old\n+new\n"


def test_diff_defaults_to_empty_string():
    assert FakeGitPort().diff(SRC, CommitSha(C1), CommitSha(C2), None) == ""


def test_log_returns_registered_commits():
    port = FakeGitPort()
    commits = [
        GitCommit(CommitSha(C2), "feat: x", "body"),
        GitCommit(CommitSha(C3), "fix: y", ""),
    ]
    port.set_log(SRC, C1, C3, commits)
    assert port.log(SRC, CommitSha(C1), CommitSha(C3), None) == commits


def test_log_defaults_to_empty_list():
    assert FakeGitPort().log(SRC, CommitSha(C1), CommitSha(C2), None) == []


def test_tag_message_returns_registered_message():
    port = FakeGitPort()
    port.set_tag_message(SRC, "v2.0.0", "Release 2.0.0\n\nBreaking changes.")
    assert port.tag_message(SRC, "v2.0.0") == "Release 2.0.0\n\nBreaking changes."


def test_tag_message_defaults_to_none():
    assert FakeGitPort().tag_message(SRC, "v9.9.9") is None


def test_is_ancestor_true_when_set():
    port = FakeGitPort()
    port.set_ancestry(SRC, C1, C2)
    assert port.is_ancestor(SRC, CommitSha(C1), CommitSha(C2)) is True


def test_is_ancestor_false_by_default_and_directional():
    port = FakeGitPort()
    port.set_ancestry(SRC, C1, C2)
    # Reverse direction was never registered.
    assert port.is_ancestor(SRC, CommitSha(C2), CommitSha(C1)) is False
    # Unrelated pair.
    assert port.is_ancestor(SRC, CommitSha(C1), CommitSha(C3)) is False


def test_sources_are_isolated():
    port = FakeGitPort()
    port.add_tag("a", "v1.0.0", C1)
    port.add_tag("b", "v2.0.0", C2)
    assert port.list_tags("a") == [GitTag("v1.0.0", CommitSha(C1))]
    assert port.list_tags("b") == [GitTag("v2.0.0", CommitSha(C2))]
