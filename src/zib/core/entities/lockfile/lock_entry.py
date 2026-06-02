"""LockEntry — the pinned reality plus the agent's conformance baseline.

This is the centerpiece of zib's correctness story. It models the conformance state
machine from the solution spec (§9.3):

    PINNED     — ``pin``: the tool's truth (what's fetched on disk). Moves ONLY via repin().
    CONFIRMED  — ``confirmed_through``: the agent's *assertion* that the code conforms
                 through this point. Set ONLY via confirm(). zib never derives or verifies it.
    SURFACED   — the transient `diff` output between confirmed and pin. NOT stored here.

The load-bearing invariant: **repin() never touches confirmed_through.** When the pin is
ahead of the confirmed baseline, that gap *is* the owed delta — the change the agent still
has to apply. Making the gap structural is how "a small change slips by unnoticed" becomes
hard to hit (intent §3.2).

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import (
    CommitSha,
    ContentHash,
    RefKind,
    RefName,
)


@dataclass(frozen=True, slots=True)
class Pin:
    """An immutable (commit, content_hash) pair — what reproduces the exact bytes.

    Used for both the current pin and a captured conformance baseline. Frozen: a pin is
    replaced, never mutated.
    """

    commit: CommitSha
    content_hash: ContentHash


@dataclass(slots=True)
class LockEntry:
    """The lock record for one reference. Behavioral methods only — no setters.

    Always-valid by construction: every field is a typed value object, so an entry can
    never hold a malformed sha/hash. The only mutations are the two domain moves below.
    """

    name: RefName
    ref_type: RefKind
    resolved: str                       # display-only label (tag / branch / short sha); never an operand
    pin: Pin
    confirmed_through: Pin | None = None

    def repin(self, *, resolved: str, ref_type: RefKind, pin: Pin) -> None:
        """update / upgrade moved the pin to a new commit.

        ``confirmed_through`` is deliberately left untouched: ``pin`` now leads
        ``confirmed_through``, and that lead is exactly the delta the agent owes. Repinning
        repeatedly without confirming accumulates the gap from the *last confirmed* point —
        nothing is silently absorbed.
        """
        self.resolved = resolved
        self.ref_type = ref_type
        self.pin = pin

    def confirm(self, baseline: Pin) -> None:
        """The agent asserts the code conforms through ``baseline``.

        Normally ``baseline`` is the current pin (the agent applied the delta and is caught
        up). For ``confirm --to`` recovery, ``baseline`` may be a retained *ancestor* of the
        pin — moving the baseline back after an over-assertion. zib records the claim; it
        never checks the code (intent §3.5 — the tool stays out of the code).

        Ancestry of ``baseline`` relative to ``pin`` is a git fact the entity cannot know
        from its own data, so the *capability* validates it before calling this
        (CLAUDE.md decision test: decide with own data → entity; needs external knowledge → caller).
        """
        self.confirmed_through = baseline

    def is_frozen(self) -> bool:
        """A rev-pinned reference never moves; polling/update is a no-op for it."""
        return self.ref_type is RefKind.REV

    def has_owed_delta(self) -> bool:
        """True when the pin leads the confirmed baseline (or nothing is confirmed yet).

        This is what `outdated` / a session hook reads to tell the agent "there is a change
        to apply here."
        """
        return (
            self.confirmed_through is None
            or self.confirmed_through.commit != self.pin.commit
        )
