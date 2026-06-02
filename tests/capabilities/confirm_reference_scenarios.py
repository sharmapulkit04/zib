"""Scenario data for the confirm_reference capability — defined once, reused by e2e.

These encode solution spec §9.3's ``confirm`` rows as concrete user journeys (CLAUDE.md:
scenarios are data with CONCRETE expected values, not shapes). Domain constants:

  PIN_COMMIT       — the current pin the agent is catching up to.
  PRIOR_COMMIT     — a retained ancestor of the pin (the one-step-back `confirm --to` target).
  UNRELATED_COMMIT — a commit that is NOT an ancestor of the pin (over-assertion recovery
                     must reject it).

Each scenario states what the agent did and the exact owed-delta / confirmed-commit outcome.
The test wires the real capability to fake stores + FakeGitPort and asserts these values.
"""

from __future__ import annotations

SOURCE = "acme/spec"
PIN_COMMIT = "a" * 40
PRIOR_COMMIT = "b" * 40
UNRELATED_COMMIT = "c" * 40

# A retained baseline tree's hash (carried by confirmed_through; integrity-checks the tree).
PRIOR_CONTENT_HASH = "sha256:" + ("b" * 64)

SCENARIOS = {
    # confirm with no arg: the agent applied the surfaced delta and is caught up to the
    # pin. The baseline advances to the current pin commit; the owed-delta gap closes.
    "confirm_no_arg_clears_owed_delta": {
        "input": {
            "name": "spec",
            "to_commit": None,
            "to_content_hash": None,
        },
        "expect": {
            "confirmed_commit": PIN_COMMIT,
            "has_owed_delta": False,
            "is_frozen": False,
        },
    },
    # confirm --to a valid retained ANCESTOR: recover an over-assertion by moving the
    # baseline BACK to the prior commit. The pin still leads the (now-earlier) baseline,
    # so the owed delta re-opens — exactly the recovery intent of spec §9.3.
    "confirm_to_ancestor_moves_baseline_back": {
        "input": {
            "name": "spec",
            "to_commit": PRIOR_COMMIT,
            "to_content_hash": PRIOR_CONTENT_HASH,
        },
        "expect": {
            "confirmed_commit": PRIOR_COMMIT,
            "has_owed_delta": True,
            "is_frozen": False,
        },
    },
}
