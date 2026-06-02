"""Scenario data for the upgrade_reference capability — defined once, reused at e2e.

Each scenario is a real user journey expressed in plain domain constants and CONCRETE
expected values (exact tags, commits, booleans), per CLAUDE.md. The capability test wires
these through the real resolve/fetch/notes gateway processes against a ``FakeGitPort`` plus
the in-memory fake stores; an e2e test later reuses the same dict through the real shell.

The single source repo for these scenarios, ``acme/spec``, has this tag history:

    v2.0.0 -> commit 'a'*40   (the pre-upgrade pin, confirmed through here)
    v2.1.0 -> commit 'b'*40   (newest in the OLD ^2 constraint)
    v3.0.0 -> commit 'c'*40   (newest overall — what ^3 selects)
    v3.1.0 -> commit 'd'*40   (even newer 3.x — what ^3 actually resolves to)

``input`` carries the new (bumped) constraint and the starting confirmed/pin state; ``expect``
carries the resolved label, the new pinned commit, the owed-delta flag (always True right
after an upgrade — repin never advances the baseline), the magnitude, and whether the
manifest constraint was rewritten to the new spec.
"""

from __future__ import annotations

SOURCE = "acme/spec"
SUBDIR = None

COMMIT_V200 = "a" * 40
COMMIT_V210 = "b" * 40
COMMIT_V300 = "c" * 40
COMMIT_V310 = "d" * 40

# Tag history registered into the fake git port for every scenario.
TAGS = [
    ("v2.0.0", COMMIT_V200),
    ("v2.1.0", COMMIT_V210),
    ("v3.0.0", COMMIT_V300),
    ("v3.1.0", COMMIT_V310),
]

# A REWRITE diff: 4 changed content lines (2 ins + 2 del) against a 2-line baseline tree →
# churn = 4 / 2 = 2.0 ≥ 0.5. The +++/--- file headers are NOT counted (diff_stats rule).
_REWRITE_DIFF = (
    "diff --git a/spec.md b/spec.md\n"
    "--- a/spec.md\n"
    "+++ b/spec.md\n"
    "@@ -1,2 +1,2 @@\n"
    "-old line one\n"
    "-old line two\n"
    "+new line one\n"
    "+new line two\n"
)
# An INCREMENTAL diff: 2 changed content lines (1 ins + 1 del) against a 100-line baseline →
# churn = 2 / 100 = 0.02 < 0.5.
_INCREMENTAL_DIFF = (
    "diff --git a/spec.md b/spec.md\n"
    "--- a/spec.md\n"
    "+++ b/spec.md\n"
    "@@ -50,1 +50,1 @@\n"
    "-clarify wording\n"
    "+clarify the wording precisely\n"
)

SCENARIOS = {
    # ^2 → ^3: jump beyond the old constraint to the newest 3.x, baseline confirmed at 2.0.0.
    # The delta anchors on the confirmed baseline (2.0.0); its tiny baseline tree + a heavy
    # diff classify as a REWRITE → the agent is told to re-read the whole reference.
    "caret_two_to_caret_three": {
        "input": {
            "name": "spec",
            "old_version": "^2.0.0",
            "new_version": "^3.0.0",
            "pinned_commit": COMMIT_V210,   # already updated within ^2 to 2.1.0
            "pinned_label": "v2.1.0",
            "confirmed_commit": COMMIT_V200,  # agent confirmed through 2.0.0
            "baseline_tree_lines": 2,         # tiny prior content
            "diff_text": _REWRITE_DIFF,
        },
        "expect": {
            "resolved": "v3.1.0",           # ^3 picks the highest 3.x tag
            "new_commit": COMMIT_V310,
            "old_commit": COMMIT_V210,
            "ref_type": "semver",
            "magnitude": "rewrite",          # churn 4/2 = 2.0 ≥ 0.5
            "owed_delta": True,              # repin never advanced confirmed_through
            "constraint_rewritten_to": "^3.0.0",
            "tag_notes": "Release v3.1.0: breaking restructure of the spec.",
        },
    },
    # ^2 → ^3 with NOTHING confirmed yet: the delta anchors on the prior pin instead, whose
    # large baseline tree + a small diff classify as INCREMENTAL.
    "caret_three_nothing_confirmed": {
        "input": {
            "name": "spec",
            "old_version": "^2.0.0",
            "new_version": "^3.0.0",
            "pinned_commit": COMMIT_V200,
            "pinned_label": "v2.0.0",
            "confirmed_commit": None,        # first encounter; never confirmed
            "baseline_tree_lines": 100,      # large prior content
            "diff_text": _INCREMENTAL_DIFF,
        },
        "expect": {
            "resolved": "v3.1.0",
            "new_commit": COMMIT_V310,
            "old_commit": COMMIT_V200,
            "ref_type": "semver",
            "magnitude": "incremental",      # churn 2/100 = 0.02 < 0.5
            "owed_delta": True,
            "constraint_rewritten_to": "^3.0.0",
            "tag_notes": "Release v3.1.0: breaking restructure of the spec.",
        },
    },
}
