"""GitCliAdapter — the real :class:`GitPort`, implemented by shelling the git CLI.

This is a *secondary adapter* (CLAUDE.md): the git gateway's processes call ``GitPort``
outward, and this adapter executes the actual ``git`` calls. It deals in wire format only —
40-hex SHAs, raw diff text, tag refs — and returns the lightly-structured port types
(:class:`GitTag`, :class:`GitCommit`, :class:`CommitSha`, :class:`TreeEntry`). All domain
transformation (semver pick, magnitude, release-note interpretation) lives in the gateway's
translators/rules, never here (invariant 8).

It works against BOTH a local filesystem path *and* a remote URL — git treats a local repo
path as a valid "remote" for ``ls-remote`` / ``fetch`` / ``clone``. For tree export it does
a minimal partial/shallow fetch of the exact commit into a throwaway temp clone, reads the
tree with ``git ls-tree``, and pulls each blob with ``git cat-file`` — producing
:class:`TreeEntry` values whose canonical content hash matches ``content_hash.py``.

A small per-source clone cache keeps repeated operations (resolve → fetch → diff → log on
the same source within one CLI invocation) from re-fetching from scratch.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry
from zib.core.gateways.git.port.git_port import GitCommit, GitPort, GitTag

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# git ls-tree mode digits → POSIX file modes used by the content_hash rule.
# git emits 100644 (regular), 100755 (executable), 120000 (symlink), 160000 (gitlink/submodule).
_LOG_SEP = "\x1e"   # record separator between commits
_FIELD_SEP = "\x1f"  # field separator within a commit record


class GitError(RuntimeError):
    """A git subprocess failed. Carries the command and stderr for a clear shell message."""


class GitCliAdapter(GitPort):
    """:class:`GitPort` backed by the system ``git`` CLI. Stateless except a clone cache."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        """Create the adapter.

        Args:
            cache_dir: optional directory under which per-source bare-ish clones are kept
                for the lifetime of this process. When omitted a fresh temp dir is created
                and removed at interpreter exit. The git adapter takes no *required* args
                (composition-root convention).
        """
        if cache_dir is None:
            self._cache_root = Path(tempfile.mkdtemp(prefix="zib-git-cache-"))
            self._owns_cache = True
        else:
            cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_root = cache_dir
            self._owns_cache = False
        # source -> path of a working clone we fetch commits into on demand.
        self._clones: dict[str, Path] = {}

    # ------------------------------------------------------------------ GitPort

    def list_tags(self, source: str) -> list[GitTag]:
        """Every tag in the source, annotated tags dereferenced to their commit.

        Uses ``git ls-remote --tags`` so no clone is needed. The ``^{}`` peeled line that
        git emits for an annotated tag overrides the tag-object line, so the commit we keep
        is always the underlying commit (never the tag object).
        """
        out = self._run(["git", "ls-remote", "--tags", self._loc(source)])
        # name -> commit hex; peeled (^{}) lines win.
        resolved: dict[str, str] = {}
        order: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            sha, _, ref = line.partition("\t")
            if not ref.startswith("refs/tags/"):
                continue
            name = ref[len("refs/tags/"):]
            peeled = name.endswith("^{}")
            if peeled:
                name = name[: -len("^{}")]
            if name not in resolved:
                order.append(name)
            if peeled or name not in resolved:
                resolved[name] = sha
        return [GitTag(name, CommitSha(resolved[name])) for name in order]

    def resolve(self, source: str, ref: str) -> CommitSha:
        """Resolve a branch / tag / rev / bare SHA to the commit it points at.

        A bare 40-hex sha resolves to itself. Otherwise ``git ls-remote`` is consulted for a
        matching branch or tag (annotated tags peeled). An unknown name raises ``KeyError``
        to match the port contract.
        """
        if _SHA_RE.match(ref):
            return CommitSha(ref)

        out = self._run(["git", "ls-remote", self._loc(source), ref, f"{ref}^{{}}", f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}"])
        branch_sha: str | None = None
        tag_sha: str | None = None
        peeled_tag_sha: str | None = None
        exact_sha: str | None = None
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            sha, _, name = line.partition("\t")
            if name == f"refs/heads/{ref}":
                branch_sha = sha
            elif name == f"refs/tags/{ref}^{{}}":
                peeled_tag_sha = sha
            elif name == f"refs/tags/{ref}":
                tag_sha = sha
            elif name == ref or name == f"{ref}^{{}}":
                exact_sha = sha
        # Branch tip wins, then a (peeled) tag, then any exact match.
        chosen = branch_sha or peeled_tag_sha or tag_sha or exact_sha
        if chosen is None:
            raise KeyError(f"unknown ref {ref!r} for source {source!r}")
        return CommitSha(chosen)

    def export_tree(
        self, source: str, commit: CommitSha, subdirectory: str | None
    ) -> list[TreeEntry]:
        """Export the tree at ``commit`` as :class:`TreeEntry` values (subdir-scoped).

        Fetches the exact commit into the source's working clone, lists the tree
        recursively with ``git ls-tree``, and reads each blob with ``git cat-file``. Symlink
        blobs are the target string bytes (git stores them that way) — the content_hash rule
        hashes them as-is, never dereferencing. Paths are scoped to ``subdirectory`` if given,
        but the returned ``path`` stays repo-relative (so the hash is stable regardless of how
        the consumer mounts it).
        """
        clone = self._ensure_commit(source, commit)
        prefix = None
        if subdirectory is not None:
            prefix = subdirectory.strip("/")
        ls_args = ["git", "-C", str(clone), "ls-tree", "-r", "-z", commit.value]
        if prefix:
            ls_args.append(prefix)
        raw = self._run(ls_args)
        entries: list[TreeEntry] = []
        for record in raw.split("\0"):
            if not record:
                continue
            # format: "<mode> <type> <sha>\t<path>"
            meta, _, path = record.partition("\t")
            mode_str, obj_type, obj_sha = meta.split(" ", 2)
            obj_sha = obj_sha.strip()
            if obj_type != "blob":
                # commit (submodule/gitlink) or tree — not a file the agent reads. Skip.
                continue
            blob = self._run_bytes(
                ["git", "-C", str(clone), "cat-file", "blob", obj_sha]
            )
            entries.append(TreeEntry(path=path, mode=int(mode_str, 8), blob=blob))
        return entries

    def diff(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> str:
        """Unified diff between two commits (subdir-scoped). Empty string if identical."""
        clone = self._ensure_commit(source, from_commit)
        self._ensure_commit(source, to_commit)
        args = [
            "git", "-C", str(clone), "diff", "--no-color",
            from_commit.value, to_commit.value,
        ]
        if subdirectory:
            args += ["--", subdirectory.strip("/")]
        return self._run(args)

    def log(
        self,
        source: str,
        from_commit: CommitSha,
        to_commit: CommitSha,
        subdirectory: str | None,
    ) -> list[GitCommit]:
        """Commit log in ``(from, to]`` (subdir-scoped), newest-first as git emits it."""
        clone = self._ensure_commit(source, from_commit)
        self._ensure_commit(source, to_commit)
        fmt = f"%H{_FIELD_SEP}%s{_FIELD_SEP}%b{_LOG_SEP}"
        args = [
            "git", "-C", str(clone), "log", f"--format={fmt}",
            f"{from_commit.value}..{to_commit.value}",
        ]
        if subdirectory:
            args += ["--", subdirectory.strip("/")]
        raw = self._run(args)
        commits: list[GitCommit] = []
        for record in raw.split(_LOG_SEP):
            record = record.strip("\n")
            if not record:
                continue
            parts = record.split(_FIELD_SEP)
            if len(parts) < 3:
                continue
            sha, subject, body = parts[0], parts[1], parts[2]
            commits.append(
                GitCommit(commit=CommitSha(sha.strip()), subject=subject, body=body.strip("\n"))
            )
        return commits

    def tag_message(self, source: str, tag: str) -> str | None:
        """The annotated-tag message, or ``None`` for a lightweight tag / unknown tag.

        A lightweight tag points straight at a commit (objecttype ``commit``) and has no
        message of its own — only an *annotated* tag (objecttype ``tag``) carries one. We
        read ``%(objecttype)`` first so we never mistake the underlying commit message for a
        tag message.
        """
        commit = self.resolve(source, tag)
        self._ensure_commit(source, commit)
        clone = self._clone_for(source)
        result = self._run_raw(
            ["git", "-C", str(clone), "for-each-ref",
             "--format=%(objecttype)%0a%(contents)", f"refs/tags/{tag}"],
        )
        if result.returncode != 0:
            return None
        text = result.stdout.decode("utf-8", "replace")
        objecttype, _, contents = text.partition("\n")
        if objecttype.strip() != "tag":
            return None  # lightweight tag — no tag object, no message
        message = contents.strip("\n")
        return message if message else None

    def is_ancestor(
        self, source: str, ancestor: CommitSha, descendant: CommitSha
    ) -> bool:
        """True if ``ancestor`` is reachable from ``descendant`` (merge-base --is-ancestor)."""
        clone = self._ensure_commit(source, ancestor)
        self._ensure_commit(source, descendant)
        result = self._run_raw(
            ["git", "-C", str(clone), "merge-base", "--is-ancestor",
             ancestor.value, descendant.value]
        )
        # exit 0 → ancestor; exit 1 → not; anything else → a real error.
        if result.returncode == 0:
            return True
        if result.returncode == 1:
            return False
        raise GitError(
            f"git merge-base --is-ancestor failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )

    # ------------------------------------------------------------------ internals

    @staticmethod
    def _loc(source: str) -> str:
        """Normalize a source into something git accepts as a remote location.

        A local path is expanded + absolutized so git treats it as a local remote; a URL
        (or scp-style ``host:path``) is passed through unchanged.
        """
        expanded = os.path.expanduser(source)
        if os.path.isdir(expanded) or os.path.isdir(os.path.join(expanded, ".git")):
            return os.path.abspath(expanded)
        return source

    def _clone_for(self, source: str) -> Path:
        """Return (creating once) a working clone with full history, blobs fetched lazily.

        On first contact this does ONE blob-filtered fetch of every ref + tag from the
        source. That brings the complete commit graph and all tag objects — so ancestry
        (``merge-base --is-ancestor``), tag messages, and log ranges are correct — while
        leaving file blobs to be lazily fetched by ``cat-file`` (the partial-clone promisor)
        only when a tree is actually exported. Cheap on big repos, correct on all of them.
        """
        if source in self._clones:
            return self._clones[source]
        # A stable per-source directory name within the cache root.
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", source)[:80]
        path = self._cache_root / f"{safe}-{abs(hash(source)) & 0xffffff:06x}"
        if not (path / ".git").exists():
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)
            path.mkdir(parents=True, exist_ok=True)
            self._run(["git", "-C", str(path), "init", "-q"])
            loc = self._loc(source)
            self._run(["git", "-C", str(path), "remote", "add", "origin", loc])
            # Try a blob-filtered full-ref fetch (partial clone). Fall back to a plain full
            # fetch when the server / local repo doesn't advertise the filter capability.
            fetched = self._run_raw(
                ["git", "-C", str(path), "fetch", "--tags", "--filter=blob:none",
                 "origin", "+refs/heads/*:refs/remotes/origin/*"]
            )
            if fetched.returncode != 0:
                self._run(
                    ["git", "-C", str(path), "fetch", "--tags", "origin",
                     "+refs/heads/*:refs/remotes/origin/*"]
                )
        self._clones[source] = path
        return path

    def _ensure_commit(self, source: str, commit: CommitSha) -> Path:
        """Ensure ``commit`` exists locally in the source's clone; fetch it if missing.

        The initial clone brings every ref's history, so a tagged/branch-reachable commit is
        already present. A bare detached commit not on any ref (rare) is fetched directly.
        """
        clone = self._clone_for(source)
        have = self._run_raw(
            ["git", "-C", str(clone), "cat-file", "-e", f"{commit.value}^{{commit}}"]
        )
        if have.returncode == 0:
            return clone
        fetched = self._run_raw(
            ["git", "-C", str(clone), "fetch", "--filter=blob:none", "origin", commit.value]
        )
        if fetched.returncode != 0:
            self._run(["git", "-C", str(clone), "fetch", "origin", commit.value])
        return clone

    def _run(self, args: list[str]) -> str:
        """Run a git command, returning decoded stdout; raise :class:`GitError` on failure."""
        result = self._run_raw(args)
        if result.returncode != 0:
            raise GitError(
                f"{' '.join(args)} failed (exit {result.returncode}): "
                f"{result.stderr.decode('utf-8', 'replace').strip()}"
            )
        return result.stdout.decode("utf-8", "replace")

    def _run_bytes(self, args: list[str]) -> bytes:
        """Run a git command, returning raw stdout bytes; raise on failure (for blobs)."""
        result = self._run_raw(args)
        if result.returncode != 0:
            raise GitError(
                f"{' '.join(args)} failed (exit {result.returncode}): "
                f"{result.stderr.decode('utf-8', 'replace').strip()}"
            )
        return result.stdout

    @staticmethod
    def _run_raw(args: list[str]) -> subprocess.CompletedProcess[bytes]:
        """Run a git command capturing raw bytes; never raises on non-zero exit."""
        env = dict(os.environ)
        # Keep git non-interactive and deterministic.
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        env.setdefault("GIT_CONFIG_NOSYSTEM", "1")
        return subprocess.run(args, capture_output=True, env=env)
