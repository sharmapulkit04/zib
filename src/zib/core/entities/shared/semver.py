"""Semantic Versioning — pure stdlib implementation.

zib resolves ``version`` constraints against a repo's tags itself rather than
pulling in a third-party semver package: core/ stays dependency-free, and the
supported subset is small, explicit, and pinned under the lockfile contract.

This module implements just what zib's manifest needs:

Versions (:class:`Version`)
    ``MAJOR.MINOR.PATCH`` with an optional dot-separated prerelease
    (``1.0.0-beta.2``). An optional leading ``v`` is accepted on parse
    (``v2.1.4``). Build metadata (``+...``) is **not** supported and makes a
    string unparseable. Ordering follows SemVer §11 precedence: a release
    outranks any of its prereleases, and prerelease identifiers compare
    field-by-field (numeric identifiers numerically and below alphanumeric
    ones; a shorter prerelease prefix is the lower version).

Ranges (:class:`Range`) — the supported subset of constraint syntax:
    * **exact**   — ``1.2.3``        matches only ``1.2.3``
    * **caret**   — ``^1.2.3``       compatible-with: ``>=1.2.3 <2.0.0``
                                     (npm rules, incl. the 0.x special cases:
                                     ``^0.2.3`` → ``>=0.2.3 <0.3.0``;
                                     ``^0.0.3`` → ``>=0.0.3 <0.0.4``)
    * **tilde**   — ``~1.2.3``       ``>=1.2.3 <1.3.0`` ; ``~1.2`` → ``>=1.2.0 <1.3.0``
                                     ; ``~1`` → ``>=1.0.0 <2.0.0``
    * **x-range** — ``1.2.x`` / ``1.x`` / ``*``   wildcard on a position
    * **wildcard**— ``*`` (or ``x`` / ``X``)      any stable version

A prerelease version is **excluded** from a range unless the spec *itself*
names a prerelease (so ``^1.2.3`` never matches ``2.0.0-rc.1``, but
``^1.2.3-rc.1`` may match prereleases of ``1.2.x``). This mirrors npm/Cargo and
keeps unstable tags out of stable constraints.

:func:`highest_satisfying` picks the greatest version a range admits — this is
how ``version`` (semver) and ``latest`` refs choose a tag.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import total_ordering
from typing import Iterable

# MAJOR.MINOR.PATCH with optional leading 'v' and optional -prerelease.
# Build metadata (+...) is intentionally unsupported.
_VERSION_RE = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)"
    r"\.(?P<minor>0|[1-9]\d*)"
    r"\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

# A single prerelease identifier is numeric when it is all digits with no
# leading zero (or just "0"). Anything else is alphanumeric.
_NUMERIC_IDENT_RE = re.compile(r"^(?:0|[1-9]\d*)$")


@total_ordering
@dataclass(frozen=True, slots=True)
class Version:
    """A parsed semantic version. Frozen, totally ordered by SemVer precedence."""

    major: int
    minor: int
    patch: int
    prerelease: tuple = ()  # tuple of str|int identifiers; () means a stable release

    @classmethod
    def parse(cls, text: str) -> "Version | None":
        """Parse ``MAJOR.MINOR.PATCH[-prerelease]`` (optional leading ``v``).

        Returns ``None`` for anything that is not a well-formed version —
        callers decide whether an unparseable tag is an error.
        """
        if not isinstance(text, str):
            return None
        match = _VERSION_RE.match(text.strip())
        if match is None:
            return None
        pre = match.group("prerelease")
        prerelease: tuple = ()
        if pre is not None:
            prerelease = tuple(_coerce_identifier(part) for part in pre.split("."))
        return cls(
            int(match.group("major")),
            int(match.group("minor")),
            int(match.group("patch")),
            prerelease,
        )

    @property
    def is_stable(self) -> bool:
        """True when this is a release (no prerelease tag)."""
        return not self.prerelease

    def _core(self) -> tuple:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        if self._core() != other._core():
            return self._core() < other._core()
        # Same core: a prerelease has LOWER precedence than the release.
        if not self.prerelease and not other.prerelease:
            return False
        if not self.prerelease:  # self is the release -> higher
            return False
        if not other.prerelease:  # other is the release -> self is lower
            return True
        return _compare_prerelease(self.prerelease, other.prerelease) < 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self._core(), self.prerelease) == (other._core(), other.prerelease)

    def __hash__(self) -> int:
        return hash((self._core(), self.prerelease))

    def __str__(self) -> str:
        core = f"{self.major}.{self.minor}.{self.patch}"
        if not self.prerelease:
            return core
        return core + "-" + ".".join(str(part) for part in self.prerelease)


def _coerce_identifier(part: str) -> "str | int":
    """A prerelease identifier becomes an int when it is purely numeric."""
    if _NUMERIC_IDENT_RE.match(part):
        return int(part)
    return part


def _compare_prerelease(left: tuple, right: tuple) -> int:
    """Compare two non-empty prerelease tuples per SemVer §11.4. -1/0/1."""
    for a, b in zip(left, right):
        a_num, b_num = isinstance(a, int), isinstance(b, int)
        if a_num and b_num:
            if a != b:
                return -1 if a < b else 1
        elif a_num != b_num:
            # Numeric identifiers always have lower precedence than alphanumeric.
            return -1 if a_num else 1
        else:  # both strings
            if a != b:
                return -1 if a < b else 1
    # All shared identifiers equal: the longer prerelease has higher precedence.
    if len(left) == len(right):
        return 0
    return -1 if len(left) < len(right) else 1


@dataclass(frozen=True)
class Range:
    """A version constraint over the supported subset (see module docstring).

    Internally a ``[lower, upper)`` window plus inclusivity flags, and whether
    prereleases are admitted (only when the spec itself named one).
    """

    lower: "Version | None"           # inclusive lower bound; None = unbounded below
    upper: "Version | None"           # exclusive upper bound; None = unbounded above
    include_prerelease: bool = False  # admit prerelease versions in the window
    raw: str = field(default="", compare=False)

    @classmethod
    def from_spec(cls, text: str) -> "Range":
        """Parse a constraint string into a Range. Raises ValueError if unsupported."""
        spec = text.strip()
        if not spec:
            raise ValueError("empty version range")

        # Bare wildcard: any stable version.
        if spec in ("*", "x", "X"):
            return cls(lower=None, upper=None, include_prerelease=False, raw=spec)

        if spec[0] == "^":
            return cls._caret(spec[1:].strip(), spec)
        if spec[0] == "~":
            return cls._tilde(spec[1:].strip(), spec)

        # x-range (e.g. 1.2.x / 1.x) — detected by a wildcard component.
        if cls._has_wildcard(spec):
            return cls._x_range(spec)

        # Otherwise it must be an exact, fully-specified version.
        version = Version.parse(spec)
        if version is None:
            raise ValueError(f"unsupported version range {text!r}")
        return cls(
            lower=version,
            upper=version,  # inclusive of exactly this version (handled in satisfies)
            include_prerelease=bool(version.prerelease),
            raw=spec,
        )

    # --- constructors per operator ----------------------------------------

    @classmethod
    def _caret(cls, body: str, raw: str) -> "Range":
        version = Version.parse(body)
        if version is None:
            raise ValueError(f"unsupported caret range {raw!r}")
        lower = version
        if version.major > 0:
            upper = Version(version.major + 1, 0, 0)
        elif version.minor > 0:
            # ^0.2.3 -> >=0.2.3 <0.3.0
            upper = Version(0, version.minor + 1, 0)
        else:
            # ^0.0.3 -> >=0.0.3 <0.0.4
            upper = Version(0, 0, version.patch + 1)
        return cls(lower=lower, upper=upper, include_prerelease=bool(version.prerelease), raw=raw)

    @classmethod
    def _tilde(cls, body: str, raw: str) -> "Range":
        # ~1, ~1.2, ~1.2.3 — patch-level changes when minor is given, else minor-level.
        nums, pre = cls._split_partial(body)
        if nums is None:
            raise ValueError(f"unsupported tilde range {raw!r}")
        if len(nums) == 1:  # ~1 -> >=1.0.0 <2.0.0
            major = nums[0]
            lower = Version(major, 0, 0)
            upper = Version(major + 1, 0, 0)
            include_pre = False
        elif len(nums) == 2:  # ~1.2 -> >=1.2.0 <1.3.0
            major, minor = nums
            lower = Version(major, minor, 0)
            upper = Version(major, minor + 1, 0)
            include_pre = False
        else:  # ~1.2.3 -> >=1.2.3 <1.3.0
            major, minor, patch = nums
            lower = Version(major, minor, patch, pre)
            upper = Version(major, minor + 1, 0)
            include_pre = bool(pre)
        return cls(lower=lower, upper=upper, include_prerelease=include_pre, raw=raw)

    @classmethod
    def _x_range(cls, raw: str) -> "Range":
        # e.g. 1.2.x / 1.x / 1.X — wildcard fixes everything to its left.
        parts = raw.split(".")
        fixed: list[int] = []
        for part in parts:
            if part in ("x", "X", "*"):
                break
            if not _NUMERIC_IDENT_RE.match(part):
                raise ValueError(f"unsupported x-range {raw!r}")
            fixed.append(int(part))
        if not fixed:
            # leading wildcard like *.x — treat as full wildcard
            return cls(lower=None, upper=None, include_prerelease=False, raw=raw)
        if len(fixed) == 1:  # 1.x -> >=1.0.0 <2.0.0
            major = fixed[0]
            return cls(Version(major, 0, 0), Version(major + 1, 0, 0), False, raw)
        # 1.2.x -> >=1.2.0 <1.3.0
        major, minor = fixed[0], fixed[1]
        return cls(Version(major, minor, 0), Version(major, minor + 1, 0), False, raw)

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _has_wildcard(spec: str) -> bool:
        return any(part in ("x", "X", "*") for part in spec.split("."))

    @staticmethod
    def _split_partial(body: str) -> "tuple[list[int] | None, tuple]":
        """Parse a partial version like ``1`` / ``1.2`` / ``1.2.3-rc.1``.

        Returns (numeric core list, prerelease tuple), or (None, ()) if invalid.
        """
        pre: tuple = ()
        core = body
        if "-" in body:
            core, _, pre_text = body.partition("-")
            if not pre_text:
                return None, ()
            pre = tuple(_coerce_identifier(p) for p in pre_text.split("."))
        parts = core.split(".")
        if not (1 <= len(parts) <= 3):
            return None, ()
        nums: list[int] = []
        for part in parts:
            if not _NUMERIC_IDENT_RE.match(part):
                return None, ()
            nums.append(int(part))
        # A prerelease is only meaningful with a full 3-part core.
        if pre and len(nums) != 3:
            return None, ()
        return nums, pre

    # --- membership -------------------------------------------------------

    def satisfies(self, version: Version) -> bool:
        """True if ``version`` falls within this range."""
        # Prerelease gate: a prerelease is admitted only when this range itself
        # named a prerelease AND it shares the same [major,minor,patch] tuple as
        # a bound (npm rule — a prerelease constraint pins prereleases to that core).
        if version.prerelease and not self.include_prerelease:
            return False
        if version.prerelease and self.include_prerelease:
            if not self._prerelease_core_allowed(version):
                return False
        if self.lower is not None and version < self.lower:
            return False
        if self.upper is not None:
            if self.lower is not None and self.lower == self.upper:
                # Exact pin: only the version itself.
                return version == self.lower
            if version >= self.upper:
                return False
        return True

    def _prerelease_core_allowed(self, version: Version) -> bool:
        """A prerelease may only match when its core equals a bound's core.

        npm: ``^1.2.3-rc.1`` admits prereleases of ``1.2.3`` only, not of any
        higher version in the window. We allow a prerelease whose
        (major,minor,patch) matches the lower bound's core.
        """
        core = (version.major, version.minor, version.patch)
        if self.lower is not None and core == (self.lower.major, self.lower.minor, self.lower.patch):
            return True
        return False

    def __str__(self) -> str:
        return self.raw


def highest_satisfying(versions: Iterable[Version], rng: Range) -> "Version | None":
    """Return the greatest version satisfying ``rng``, or None if none do."""
    candidates = [v for v in versions if rng.satisfies(v)]
    if not candidates:
        return None
    return max(candidates)
