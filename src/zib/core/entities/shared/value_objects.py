"""Immutable value objects — make illegal states unrepresentable.

Per CLAUDE.md: value objects are immutable (frozen), replaced not edited, defined
once in shared/. When a value object cannot be *constructed* in an invalid state,
every entity that holds it is relieved of re-checking that invariant. So the guards
live here, at the type boundary, and nowhere downstream.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class RefName:
    """A reference's primary key — lowercase, ``[a-z][a-z0-9-]*``.

    This is the stable handle the manifest, lockfile, on-disk tree, and the agent's
    notes all key on. Constraining it keeps it safe as a filesystem path segment.
    """

    value: str

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.value):
            raise ValueError(
                f"invalid reference name {self.value!r}: must match [a-z][a-z0-9-]*"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Role:
    """The need a reference fills (its "slot", e.g. ``json-mapping``).

    Swap replaces *the reference filling a role*. Free-form, single-line, non-empty.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.strip() != self.value or "\n" in self.value:
            raise ValueError(
                f"invalid role {self.value!r}: must be a non-empty single-line label"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class CommitSha:
    """A full 40-hex git commit SHA — the immutable pin."""

    value: str

    def __post_init__(self) -> None:
        if not _SHA_RE.match(self.value):
            raise ValueError(
                f"invalid commit SHA {self.value!r}: expected 40 lowercase hex chars"
            )

    def short(self) -> str:
        return self.value[:7]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class ContentHash:
    """``sha256:<64-hex>`` over an exported tree — the reproducibility anchor.

    Constructed only with a well-formed value; the canonical hashing lives in the
    ``content_hash`` rule, which returns one of these.
    """

    value: str

    def __post_init__(self) -> None:
        if not _CONTENT_HASH_RE.match(self.value):
            raise ValueError(
                f"invalid content hash {self.value!r}: expected 'sha256:<64 hex>'"
            )

    def __str__(self) -> str:
        return self.value


class RefKind(str, Enum):
    """The five ways a reference can be tracked. Exactly one applies per reference."""

    SEMVER = "semver"   # a version constraint matched against release tags (range, exact, or x-ranges)
    TAG = "tag"         # a literal release tag, taken as-is (no semver interpretation)
    LATEST = "latest"   # the highest release tag at resolve time
    BRANCH = "branch"   # a branch tip (moving; the commit log stands in for release notes)
    REV = "rev"         # a frozen commit SHA (never moves)


@dataclass(frozen=True, slots=True)
class RefSpec:
    """What the manifest asks zib to track — exactly ONE ref kind.

    The manifest's mutually-exclusive keys (``version`` / ``branch`` / ``tag`` / ``rev``)
    are collapsed into a single RefSpec at construction, so no entity downstream can ever
    hold an ambiguous spec. A manifest carrying two of those keys is a parse error
    (solution spec §4) — enforced in :meth:`from_manifest`.
    """

    kind: RefKind
    value: str | None  # semver range / literal tag / branch name / 40-hex sha; None only for LATEST

    def __post_init__(self) -> None:
        if self.kind is RefKind.LATEST:
            if self.value is not None:
                raise ValueError("RefSpec(latest) takes no value")
            return
        if not self.value:
            raise ValueError(f"RefSpec({self.kind.value}) requires a value")
        if self.kind is RefKind.REV and not _SHA_RE.match(self.value):
            raise ValueError(
                f"RefSpec(rev) requires a 40-hex commit SHA, got {self.value!r}"
            )

    @staticmethod
    def from_manifest(
        *,
        version: str | None = None,
        branch: str | None = None,
        tag: str | None = None,
        rev: str | None = None,
    ) -> "RefSpec":
        """Collapse the manifest's mutually-exclusive ref keys into one RefSpec.

        Exactly one of ``version`` / ``branch`` / ``tag`` / ``rev`` must be set.
        ``version`` is the semver lane: ``"latest"`` → LATEST, anything else → SEMVER
        (a range like ``^2.1.0`` or an exact version like ``2.1.4`` — the resolution rule
        disambiguates against the live tag list). ``tag`` is the *literal* lane (no semver).
        """
        given = {
            key: val
            for key, val in (
                ("version", version),
                ("branch", branch),
                ("tag", tag),
                ("rev", rev),
            )
            if val is not None
        }
        if len(given) != 1:
            raise ValueError(
                "a reference must declare exactly one of version/branch/tag/rev; "
                f"got {sorted(given)}"
            )
        key, val = next(iter(given.items()))
        if key == "branch":
            return RefSpec(RefKind.BRANCH, val)
        if key == "tag":
            return RefSpec(RefKind.TAG, val)
        if key == "rev":
            return RefSpec(RefKind.REV, val)
        # version lane
        if val == "latest":
            return RefSpec(RefKind.LATEST, None)
        return RefSpec(RefKind.SEMVER, val)


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """One file in an exported reference tree — a pure, filesystem-free representation.

    The git gateway / content store produces these; the ``content_hash`` rule consumes
    them. ``mode`` is the POSIX file mode (regular ``0o100644``, executable ``0o100755``,
    symlink ``0o120000``). For a symlink, ``blob`` is the *target string* as UTF-8 bytes —
    the rule hashes it as-is and never dereferences it.
    """

    path: str   # POSIX-relative path within the exported tree
    mode: int
    blob: bytes


SYMLINK_MODE = 0o120000
