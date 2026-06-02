"""Scenario data for the ``update_reference`` capability.

Defined once as plain domain constants with CONCRETE expected values, then run by
``test_update_reference.py`` (real rules + real gateway processes wired to
FakeGitPort + fake stores) and reused by e2e later (CLAUDE.md: scenarios defined
once, run at two levels).

A scenario's ``input`` describes the world to set up:
  * ``source``      — the repo coordinate the manifest declares.
  * ``name``/``role``/``description`` — the declared reference.
  * ``spec``        — the manifest constraint as (kind, value) for RefSpec.from_manifest
                      style keys: one of version/branch/tag.
  * ``tags``        — release tags to register: list of (name, commit_hex).
  * ``branch``      — optional (branch_name, commit_hex) for branch-tracked refs.
  * ``pinned``      — the lock's current pin: (commit_hex, content_hash).
  * ``confirmed``   — the lock's confirmed baseline: (commit_hex, content_hash) or None.
  * ``from_tree``   — files at the OLD pin (drives churn denominator + materialize).
  * ``to_tree``     — files at the NEW resolved commit.
  * ``diff``        — unified diff text registered for (old, new); drives churn.
  * ``to_tag``      — the tag the new commit resolves through (for tag_message lookup),
                      or None for branch refs.
  * ``tag_message`` — optional release notes for ``to_tag``.

``expect`` asserts the exact UpdateResult fields + observable store state.
"""

from __future__ import annotations

# Distinct 40-hex commit SHAs used across scenarios.
C_OLD = "1" * 40
C_NEW = "2" * 40
C_BRANCH_NEW = "3" * 40

H_OLD = "sha256:" + "a" * 64
H_BASELINE = "sha256:" + "a" * 64

# A small diff (1 insertion + 1 deletion) against a large baseline → INCREMENTAL.
SMALL_DIFF = (
    "diff --git a/spec.md b/spec.md\n"
    "--- a/spec.md\n"
    "+++ b/spec.md\n"
    "@@ -1,2 +1,2 @@\n"
    "-old line\n"
    "+new line\n"
)

# A high-churn diff (5 ins + 5 del) against a tiny 2-line baseline → REWRITE.
BIG_DIFF = (
    "diff --git a/spec.md b/spec.md\n"
    "--- a/spec.md\n"
    "+++ b/spec.md\n"
    "@@ @@\n" + ("-old\n" * 5) + ("+new\n" * 5)
)


SCENARIOS = {
    # update repins to the new commit AND confirmed_through stays at the old
    # baseline, so the moved pin owes a delta (has_owed_delta() is True).
    "semver_update_repins_and_owes_delta": {
        "input": {
            "source": "acme/spec",
            "name": "spec",
            "role": "json-mapping",
            "description": "JSON mapping conventions",
            "spec": ("version", "^2.0.0"),
            "tags": [("v2.0.0", C_OLD), ("v2.1.0", C_NEW)],
            "branch": None,
            "pinned": (C_OLD, H_OLD),
            "seed_resolved": "v2.0.0",         # lock currently shows the old tag
            "confirmed": (C_OLD, H_BASELINE),
            "from_tree": [("spec.md", 200)],   # 200-line baseline → small churn
            "to_tree": [("spec.md", 200)],
            "diff": SMALL_DIFF,
            "to_tag": "v2.1.0",
            "tag_message": "Release 2.1.0 — clarified mapping rules",
        },
        "expect": {
            "up_to_date": False,
            "old_commit": "1111111",
            "new_commit": "2222222",
            "resolved_label": "v2.1.0",
            "ref_type": "semver",
            "magnitude": "incremental",
            "has_owed_delta": True,
            "confirmed_commit": C_OLD,   # baseline UNTOUCHED
            "pin_commit": C_NEW,
            "tag_notes": "Release 2.1.0 — clarified mapping rules",
            "inventory_has_update_pending": True,
        },
    },
    # update when already newest → up_to_date True, no mutation at all.
    "already_newest_is_up_to_date": {
        "input": {
            "source": "acme/spec",
            "name": "spec",
            "role": "json-mapping",
            "description": "JSON mapping conventions",
            "spec": ("version", "^2.0.0"),
            "tags": [("v2.0.0", C_OLD), ("v2.1.0", C_NEW)],
            "branch": None,
            "pinned": (C_NEW, H_OLD),         # already on the highest-in-range
            "seed_resolved": "v2.1.0",        # lock already shows the newest tag
            "confirmed": (C_NEW, H_BASELINE),
            "from_tree": [("spec.md", 200)],
            "to_tree": [("spec.md", 200)],
            "diff": SMALL_DIFF,
            "to_tag": "v2.1.0",
            "tag_message": None,
        },
        "expect": {
            "up_to_date": True,
            "old_commit": "2222222",
            "new_commit": "2222222",
            "resolved_label": "v2.1.0",   # unchanged (no repin)
            "ref_type": "semver",
            "magnitude": None,
            "has_owed_delta": False,
            "confirmed_commit": C_NEW,
            "pin_commit": C_NEW,
            "tag_notes": None,
            "inventory_has_update_pending": False,
        },
    },
    # a high-churn update reports magnitude REWRITE.
    "high_churn_update_is_rewrite": {
        "input": {
            "source": "acme/spec",
            "name": "spec",
            "role": "json-mapping",
            "description": "JSON mapping conventions",
            "spec": ("version", "^2.0.0"),
            "tags": [("v2.0.0", C_OLD), ("v2.1.0", C_NEW)],
            "branch": None,
            "pinned": (C_OLD, H_OLD),
            "seed_resolved": "v2.0.0",
            "confirmed": (C_OLD, H_BASELINE),
            "from_tree": [("spec.md", 2)],     # tiny 2-line baseline → huge churn
            "to_tree": [("spec.md", 12)],
            "diff": BIG_DIFF,                  # churn (5+5)/2 = 5.0 → REWRITE
            "to_tag": "v2.1.0",
            "tag_message": "Release 2.1.0 — complete rewrite",
        },
        "expect": {
            "up_to_date": False,
            "old_commit": "1111111",
            "new_commit": "2222222",
            "resolved_label": "v2.1.0",
            "ref_type": "semver",
            "magnitude": "rewrite",
            "has_owed_delta": True,
            "confirmed_commit": C_OLD,
            "pin_commit": C_NEW,
            "tag_notes": "Release 2.1.0 — complete rewrite",
            "inventory_has_update_pending": True,
        },
    },
    # branch-tracked update: re-resolves the tip, repins, no tag notes (provisional).
    "branch_tip_update_repins_no_tag_notes": {
        "input": {
            "source": "acme/spec",
            "name": "spec",
            "role": "json-mapping",
            "description": "JSON mapping conventions",
            "spec": ("branch", "main"),
            "tags": [],
            "branch": ("main", C_BRANCH_NEW),
            "pinned": (C_OLD, H_OLD),
            "seed_resolved": "main",
            "confirmed": (C_OLD, H_BASELINE),
            "from_tree": [("spec.md", 200)],
            "to_tree": [("spec.md", 200)],
            "diff": SMALL_DIFF,
            "to_tag": None,
            "tag_message": None,
        },
        "expect": {
            "up_to_date": False,
            "old_commit": "1111111",
            "new_commit": "3333333",
            "resolved_label": "main",
            "ref_type": "branch",
            "magnitude": "incremental",
            "has_owed_delta": True,
            "confirmed_commit": C_OLD,
            "pin_commit": C_BRANCH_NEW,
            "tag_notes": None,            # branch refs surface no release notes
            "inventory_has_update_pending": True,
        },
    },
}
