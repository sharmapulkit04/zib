"""FakeGitPort — an in-memory test double for :class:`GitPort`.

This is the validated fake the Gateway and Capability phases build on. It satisfies the
``GitPort`` Protocol exactly (verified by ``test_git_port_contract.py`` against the
``@runtime_checkable`` protocol), so anything wired against ``GitPort`` can be exercised in
milliseconds with no git CLI and no network.

Design: everything is keyed first by ``source`` (the repo identifier), then by the relevant
sub-key. Nothing is fabricated — the read methods return *exactly* what the setup API
registered, with these sensible defaults for the never-registered case:

    list_tags    -> []            (no tags registered for the source)
    resolve      -> raises        (KeyError for unknown name; ValueError for non-40-hex unknown sha)
    export_tree  -> raises KeyError   (a tree must be explicitly set; "unknown commit" is a bug)
    diff         -> ''            (empty diff)
    log          -> []            (no commits)
    tag_message  -> None          (unannotated / no message)
    is_ancestor  -> False         (not an ancestor unless explicitly set)

Setup API (chainable assignment, all return None):

    add_tag(source, name, commit_hex)           register a release tag -> commit
    set_branch(source, branch, commit_hex)      register a branch tip -> commit
    add_rev(source, commit_hex)                 register a resolvable commit (for resolve())
    set_tree(source, commit_hex, entries)       register the exported tree at a commit
    set_diff(source, from_hex, to_hex, text)    register a unified diff for a commit pair
    set_log(source, from_hex, to_hex, commits)  register the commit log for a pair
    set_tag_message(source, tag, msg)           register an annotated-tag message
    set_ancestry(source, ancestor_hex, descendant_hex, value=True)  register an ancestry edge

``resolve`` semantics (matches the real port's documented contract):
    - if ``ref`` is a registered branch name -> that branch's commit
    - elif ``ref`` is a registered tag name   -> that tag's commit
    - elif ``ref`` is a registered rev OR a 40-hex sha -> ``CommitSha(ref)``
    - else: KeyError (unknown name) for non-sha, ValueError for malformed sha-ish input

Adding a tag / branch / rev also registers its commit as resolvable, so a tag/branch name and
its underlying sha both resolve consistently.
"""

from __future__ import annotations

import re

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry
from zib.core.gateways.git.port.git_port import GitCommit, GitPort, GitTag

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class FakeGitPort(GitPort):
    """In-memory :class:`GitPort` implementation driven entirely by the setup API."""

    def __init__(self) -> None:
        # source -> ordered list of GitTag (insertion order = registration order)
        self._tags: dict[str, list[GitTag]] = {}
        # source -> {branch name -> commit hex}
        self._branches: dict[str, dict[str, str]] = {}
        # source -> set of registered commit hexes (resolvable revs)
        self._revs: dict[str, set[str]] = {}
        # source -> {commit hex -> list[TreeEntry]}
        self._trees: dict[str, dict[str, list[TreeEntry]]] = {}
        # source -> {(from hex, to hex) -> diff text}
        self._diffs: dict[str, dict[tuple[str, str], str]] = {}
        # source -> {(from hex, to hex) -> list[GitCommit]}
        self._logs: dict[str, dict[tuple[str, str], list[GitCommit]]] = {}
        # source -> {tag name -> message}
        self._tag_messages: dict[str, dict[str, str]] = {}
        # source -> set of (ancestor hex, descendant hex) edges known to be ancestral
        self._ancestry: dict[str, set[tuple[str, str]]] = {}

    # ------------------------------------------------------------------ setup API

    def add_tag(self, source: str, name: str, commit_hex: str) -> None:
        """Register a release tag pointing at ``commit_hex``; the commit becomes resolvable."""
        self._tags.setdefault(source, []).append(GitTag(name, CommitSha(commit_hex)))
        self._revs.setdefault(source, set()).add(commit_hex)

    def set_branch(self, source: str, branch: str, commit_hex: str) -> None:
        """Register a branch tip at ``commit_hex``; the commit becomes resolvable."""
        self._branches.setdefault(source, {})[branch] = commit_hex
        self._revs.setdefault(source, set()).add(commit_hex)

    def add_rev(self, source: str, commit_hex: str) -> None:
        """Register a bare commit as resolvable (a frozen rev)."""
        self._revs.setdefault(source, set()).add(commit_hex)

    def set_tree(self, source: str, commit_hex: str, entries: list[TreeEntry]) -> None:
        """Register the exported tree at ``commit_hex``."""
        self._trees.setdefault(source, {})[commit_hex] = list(entries)

    def set_diff(self, source: str, from_hex: str, to_hex: str, text: str) -> None:
        """Register the unified diff for the ``(from, to]`` commit pair."""
        self._diffs.setdefault(source, {})[(from_hex, to_hex)] = text

    def set_log(
        self, source: str, from_hex: str, to_hex: str, commits: list[GitCommit]
    ) -> None:
        """Register the commit log for the ``(from, to]`` commit pair."""
        self._logs.setdefault(source, {})[(from_hex, to_hex)] = list(commits)

    def set_tag_message(self, source: str, tag: str, msg: str) -> None:
        """Register an annotated-tag message (producer release notes)."""
        self._tag_messages.setdefault(source, {})[tag] = msg

    def set_ancestry(
        self, source: str, ancestor_hex: str, descendant_hex: str, value: bool = True
    ) -> None:
        """Register (or, with ``value=False``, clear) an ancestry edge."""
        edges = self._ancestry.setdefault(source, set())
        edge = (ancestor_hex, descendant_hex)
        if value:
            edges.add(edge)
        else:
            edges.discard(edge)

    # ------------------------------------------------------------------ GitPort

    def list_tags(self, source: str) -> list[GitTag]:
        # Copy so callers can't mutate our registration order in place.
        return list(self._tags.get(source, []))

    def resolve(self, source: str, ref: str) -> CommitSha:
        branches = self._branches.get(source, {})
        if ref in branches:
            return CommitSha(branches[ref])
        for tag in self._tags.get(source, []):
            if tag.name == ref:
                return tag.commit
        if ref in self._revs.get(source, set()):
            return CommitSha(ref)
        if _SHA_RE.match(ref):
            # A well-formed sha that was never registered still resolves to itself —
            # the real port resolves any reachable 40-hex commit.
            return CommitSha(ref)
        raise KeyError(f"unknown ref {ref!r} for source {source!r}")

    def export_tree(
        self, source: str, commit: CommitSha, subdirectory: str | None
    ) -> list[TreeEntry]:
        trees = self._trees.get(source, {})
        key = commit.value
        if key not in trees:
            raise KeyError(
                f"no tree registered for commit {commit.short()} in source {source!r}"
            )
        entries = trees[key]
        if subdirectory is None:
            return list(entries)
        prefix = subdirectory.rstrip("/") + "/"
        return [e for e in entries if e.path.startswith(prefix)]

    def diff(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> str:
        return self._diffs.get(source, {}).get(
            (from_commit.value, to_commit.value), ""
        )

    def log(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> list[GitCommit]:
        return list(
            self._logs.get(source, {}).get((from_commit.value, to_commit.value), [])
        )

    def tag_message(self, source: str, tag: str) -> str | None:
        return self._tag_messages.get(source, {}).get(tag)

    def is_ancestor(
        self, source: str, ancestor: CommitSha, descendant: CommitSha
    ) -> bool:
        return (ancestor.value, descendant.value) in self._ancestry.get(source, set())
