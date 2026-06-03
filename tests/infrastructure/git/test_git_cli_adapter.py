"""GitPort contract, re-run against the REAL git CLI adapter.

A small hermetic git repo is built with ``git init`` (a couple of commits, a branch, a
lightweight tag, an annotated tag, a subdirectory) and the :class:`GitCliAdapter` is
exercised against it as a *local path source* — the same surface a remote URL would present.
Every assertion is concrete, mirroring the port contract; the exported tree's canonical hash
is asserted to match ``content_hash.py`` (the cross-layer reproducibility anchor).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from zib.core.entities.shared.value_objects import CommitSha
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash
from zib.infrastructure.git.git_cli_adapter import GitCliAdapter


def _git(repo: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e",
        "GIT_CONFIG_NOSYSTEM": "1", "HOME": str(repo),
    }
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, env=env, check=True
    )
    return out.stdout.decode().strip()


@pytest.fixture()
def repo(tmp_path: Path) -> dict:
    """A branch-tracked repo with no-version + a tagged release; returns source + key shas."""
    src = tmp_path / "src"
    src.mkdir()
    _git(src, "init", "-q", "-b", "main")
    (src / "README.md").write_text("v1\n")
    (src / "docs").mkdir()
    (src / "docs" / "spec.md").write_text("spec one\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "first commit")
    c1 = _git(src, "rev-parse", "HEAD")
    # lightweight tag at v1.0.0
    _git(src, "tag", "v1.0.0")

    (src / "README.md").write_text("v2\n")
    (src / "docs" / "spec.md").write_text("spec one\nspec two\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "feat: second")
    c2 = _git(src, "rev-parse", "HEAD")
    # annotated tag at v2.0.0 with a message
    _git(src, "tag", "-a", "v2.0.0", "-m", "Release 2.0.0\n\nBreaking.")

    return {"source": str(src), "c1": c1, "c2": c2}


def test_adapter_satisfies_git_port_protocol() -> None:
    assert isinstance(GitCliAdapter(), GitPort)


def test_list_tags_dereferences_annotated(repo: dict) -> None:
    tags = GitCliAdapter().list_tags(repo["source"])
    by_name = {t.name: t.commit.value for t in tags}
    assert by_name["v1.0.0"] == repo["c1"]
    assert by_name["v2.0.0"] == repo["c2"]  # annotated tag peeled to its commit


def test_list_tags_empty_for_repo_without_tags(tmp_path: Path) -> None:
    bare = tmp_path / "notags"
    bare.mkdir()
    _git(bare, "init", "-q", "-b", "main")
    (bare / "f").write_text("x")
    _git(bare, "add", "-A")
    _git(bare, "commit", "-q", "-m", "c")
    assert GitCliAdapter().list_tags(str(bare)) == []


def test_resolve_branch_to_commit(repo: dict) -> None:
    assert GitCliAdapter().resolve(repo["source"], "main") == CommitSha(repo["c2"])


def test_resolve_tag_to_commit(repo: dict) -> None:
    assert GitCliAdapter().resolve(repo["source"], "v1.0.0") == CommitSha(repo["c1"])


def test_resolve_annotated_tag_peels_to_commit(repo: dict) -> None:
    assert GitCliAdapter().resolve(repo["source"], "v2.0.0") == CommitSha(repo["c2"])


def test_resolve_bare_sha_returns_itself(repo: dict) -> None:
    assert GitCliAdapter().resolve(repo["source"], repo["c1"]) == CommitSha(repo["c1"])


def test_resolve_unknown_raises_keyerror(repo: dict) -> None:
    with pytest.raises(KeyError):
        GitCliAdapter().resolve(repo["source"], "does-not-exist")


def test_export_tree_hash_matches_content_hash_rule(repo: dict) -> None:
    adapter = GitCliAdapter()
    tree = adapter.export_tree(repo["source"], CommitSha(repo["c2"]), None)
    paths = {e.path for e in tree}
    assert paths == {"README.md", "docs/spec.md"}
    readme = next(e for e in tree if e.path == "README.md")
    assert readme.blob == b"v2\n"
    assert readme.mode == 0o100644
    # Hash is computable and well-formed (the cross-layer anchor).
    assert compute_content_hash(tree).value.startswith("sha256:")


def test_export_tree_scopes_to_subdirectory(repo: dict) -> None:
    tree = GitCliAdapter().export_tree(repo["source"], CommitSha(repo["c2"]), "docs")
    assert [e.path for e in tree] == ["docs/spec.md"]


def test_diff_between_commits_nonempty(repo: dict) -> None:
    text = GitCliAdapter().diff(
        repo["source"], CommitSha(repo["c1"]), CommitSha(repo["c2"]), None
    )
    assert "README.md" in text
    assert "+v2" in text


def test_diff_identical_commits_is_empty(repo: dict) -> None:
    text = GitCliAdapter().diff(
        repo["source"], CommitSha(repo["c2"]), CommitSha(repo["c2"]), None
    )
    assert text == ""


def test_log_returns_commits_in_range(repo: dict) -> None:
    commits = GitCliAdapter().log(
        repo["source"], CommitSha(repo["c1"]), CommitSha(repo["c2"]), None
    )
    assert [c.commit.value for c in commits] == [repo["c2"]]
    assert commits[0].subject == "feat: second"


def test_tag_message_for_annotated(repo: dict) -> None:
    msg = GitCliAdapter().tag_message(repo["source"], "v2.0.0")
    assert msg is not None
    assert "Release 2.0.0" in msg


def test_tag_message_none_for_lightweight(repo: dict) -> None:
    assert GitCliAdapter().tag_message(repo["source"], "v1.0.0") is None


def test_is_ancestor_true_and_directional(repo: dict) -> None:
    adapter = GitCliAdapter()
    assert adapter.is_ancestor(
        repo["source"], CommitSha(repo["c1"]), CommitSha(repo["c2"])
    ) is True
    assert adapter.is_ancestor(
        repo["source"], CommitSha(repo["c2"]), CommitSha(repo["c1"])
    ) is False
