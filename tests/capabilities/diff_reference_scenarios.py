"""Scenario data for the diff_reference capability — defined once, reused by e2e.

These encode solution spec §9.2's read-only ``diff`` outcomes as concrete user journeys
(CLAUDE.md: scenarios are data with CONCRETE expected values, not shapes). The three
states are decided purely from the lock entry's conformance position:

  - **pending delta** — the baseline (``confirmed_through``) sits at PRIOR_COMMIT while the
    pin leads at PIN_COMMIT. ``diff`` surfaces the change across (PRIOR_COMMIT, PIN_COMMIT].
  - **no owed delta** — the baseline already sits at the pin; nothing to apply.
  - **never confirmed** — first encounter, no baseline; the agent reads the WHOLE reference.

Domain constants:

  SOURCE         — the repo the reference is pinned from.
  PRIOR_COMMIT   — the confirmed baseline commit (also the diff's from-side).
  PIN_COMMIT     — the current pin commit (the diff's to-side).
  SUBDIRECTORY   — None (whole-repo reference; the gateway diff scopes by this).

Diff sizing (so the surfaced delta classifies INCREMENTAL, churn < 0.5):
  the from-side (PRIOR_COMMIT) tree has BASELINE_LINES newline-terminated lines, and the
  registered unified diff is one small hunk (1 insertion, 1 deletion) → churn = 2/20 = 0.1.

The test wires the real capability + real NotesProcess to fake stores + FakeGitPort and
asserts these exact outcomes.
"""

from __future__ import annotations

SOURCE = "acme/spec"
PRIOR_COMMIT = "b" * 40
PIN_COMMIT = "a" * 40
SUBDIRECTORY = None

# Content hashes carried by the pin / confirmed baseline (shape only — diff is tree-to-tree
# but the entity needs well-formed hashes to construct).
PIN_CONTENT_HASH = "sha256:" + ("a" * 64)
PRIOR_CONTENT_HASH = "sha256:" + ("b" * 64)

# The from-side baseline tree's line count (denominator for the churn ratio).
BASELINE_LINES = 20

# A small incremental diff: one file, one inserted + one deleted content line.
INCREMENTAL_DIFF = (
    "diff --git a/spec.md b/spec.md\n"
    "--- a/spec.md\n"
    "+++ b/spec.md\n"
    "@@ -3,1 +3,1 @@\n"
    "-old constraint sentence\n"
    "+new constraint sentence\n"
)

# A commit subject surfaced alongside the diff (the per-commit log for the range).
COMMIT_SUBJECT = "Tighten the constraint wording"

SCENARIOS = {
    # The pin leads the confirmed baseline by one commit: an owed delta exists, and a
    # read-only diff surfaces it without mutating anything. The change is small relative
    # to the baseline (churn 0.1) → INCREMENTAL, so the agent applies it line-by-line
    # (read_whole stays False).
    "pending_incremental_delta_is_surfaced": {
        "input": {"name": "spec"},
        "expect": {
            "has_pending": True,
            "read_whole": False,
            "has_delta": True,
        },
    },
    # The baseline already sits at the current pin: caught up, nothing to apply. diff
    # reports no unconfirmed changes (has_pending False) and computes no delta.
    "no_owed_delta_when_caught_up": {
        "input": {"name": "spec"},
        "expect": {
            "has_pending": False,
            "read_whole": False,
            "has_delta": False,
        },
    },
    # First encounter — nothing confirmed yet. There is no baseline to diff against, so
    # the agent reads the WHOLE reference (`zib cat`): read_whole True, has_pending True,
    # and no delta is computed.
    "never_confirmed_reads_whole": {
        "input": {"name": "spec"},
        "expect": {
            "has_pending": True,
            "read_whole": True,
            "has_delta": False,
        },
    },
}
