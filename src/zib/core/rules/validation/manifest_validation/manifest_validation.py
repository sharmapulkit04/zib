"""Friendly boundary validation for a reference declaration.

This is the *collecting* validator the ``add`` / parse paths run BEFORE constructing
any value object. Value objects (``RefName``, ``Role``, ``RefSpec``) are always-valid and
*raise* on the first bad input — great for an invariant wall, hostile as a user-facing
gate. This rule mirrors their constraints but accumulates every violation as a
human-readable string so the caller can report all problems at once and never construct
a half-valid entity.

Pure stdlib only — this is core/. It returns a list of strings; empty means valid.
"""

from __future__ import annotations

import re

# Mirrors RefName's constraint (value_objects._NAME_RE) — kept local so this rule
# stays a pure leaf with no dependency on raising constructors.
_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# owner/repo shorthand: a single slash, each side a plausible path segment.
_OWNER_REPO_RE = re.compile(r"^[^/\s]+/[^/\s]+$")
# URL-ish sources: http(s)://, git://, ssh://, or scp-style git@host:owner/repo.
_URL_RE = re.compile(r"^(https?|git|ssh)://\S+$")
_SCP_RE = re.compile(r"^[^@\s]+@[^:\s]+:\S+$")


def _looks_like_source(source: str) -> bool:
    """True if ``source`` plausibly names one of zib's v1 source forms.

    Accepts ``owner/repo`` shorthand, a URL (http/https/git/ssh), an scp-style git
    remote (``git@host:owner/repo``), or a filesystem path (absolute, ``~``-rooted,
    or relative ``./`` / ``../``). This is intentionally permissive — the git gateway
    does authoritative resolution; here we only reject the obviously-not-a-source.
    """
    if _URL_RE.match(source) or _SCP_RE.match(source):
        return True
    if source.startswith(("/", "~", "./", "../")) or source.endswith(".git"):
        return True
    if _OWNER_REPO_RE.match(source):
        return True
    return False


def validate_reference(
    *,
    name: str,
    role: str,
    source: str,
    version: str | None = None,
    branch: str | None = None,
    tag: str | None = None,
    rev: str | None = None,
    subdirectory: str | None = None,
) -> list[str]:
    """Collect every boundary violation in a reference declaration.

    Returns an empty list when the declaration is valid. Each violation is a separate,
    human-readable string; multiple violations accumulate. This never raises — it is the
    gate that runs *before* value-object construction.
    """
    violations: list[str] = []

    # name — same shape as RefName.
    if not _NAME_RE.match(name):
        violations.append(
            f"invalid name {name!r}: must match [a-z][a-z0-9-]* "
            "(lowercase letter first, then letters/digits/hyphens)"
        )

    # role — non-empty, single-line, no leading/trailing whitespace.
    if not role or role.strip() != role or "\n" in role:
        violations.append(
            f"invalid role {role!r}: must be a non-empty single-line label"
        )

    # source — non-empty and plausibly one of the supported forms.
    if not source or not source.strip():
        violations.append("missing source: a git source is required")
    elif not _looks_like_source(source):
        violations.append(
            f"invalid source {source!r}: expected 'owner/repo', a URL "
            "(http/https/git/ssh), or a filesystem path"
        )

    # exactly one of version/branch/tag/rev.
    given = [
        key
        for key, val in (
            ("version", version),
            ("branch", branch),
            ("tag", tag),
            ("rev", rev),
        )
        if val is not None
    ]
    if len(given) == 0:
        violations.append(
            "no ref specified: provide exactly one of version/branch/tag/rev"
        )
    elif len(given) > 1:
        violations.append(
            "ambiguous ref: provide exactly one of version/branch/tag/rev, "
            f"got {', '.join(sorted(given))}"
        )

    # rev (if given) must be a full 40-hex SHA.
    if rev is not None and not _SHA_RE.match(rev):
        violations.append(
            f"invalid rev {rev!r}: expected a 40-character lowercase hex commit SHA"
        )

    # subdirectory (if given) must be a relative, traversal-free path.
    if subdirectory is not None:
        if subdirectory.startswith("/"):
            violations.append(
                f"invalid subdirectory {subdirectory!r}: must be relative, not absolute"
            )
        if ".." in subdirectory.split("/"):
            violations.append(
                f"invalid subdirectory {subdirectory!r}: must not contain '..' segments"
            )

    return violations
