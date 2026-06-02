"""Scenario data for the swap_reference capability — defined once, reused at every level.

These are real user journeys expressed in plain domain constants and CONCRETE expected
values (exact names, labels, booleans), per CLAUDE.md. The capability test wires them with
real rules + real gateway processes against a ``FakeGitPort`` and fake stores; the same
SCENARIOS are reused by the app e2e layer later through a real shell.

Domain vocabulary:
  * ``role`` — the slot being swapped (preserved across the swap).
  * ``old`` / ``new`` — the references swapped out / in; each is (name, source, version tag).
  * ``expect`` — what must be true of the persisted manifest + lockfile + content after.

The defining swap fact (intent §3.3, solution spec §8.2): the new reference is added under
the SAME role with a RESET conformance baseline, so it carries an owed delta (True) and the
old reference is gone from manifest, lockfile, and content.
"""

from __future__ import annotations

SCENARIOS = {
    # The headline journey: a better mapping library replaces the current one for the slot.
    "swap_within_role": {
        "input": {
            "role": "json-mapping",
            "old": {"name": "jackson", "source": "acme/jackson", "tag": "v2.16.0"},
            "new": {"name": "moshi", "source": "acme/moshi", "tag": "v1.15.0"},
        },
        "expect": {
            "result_role": "json-mapping",
            "result_removed_name": "jackson",
            "result_added_name": "moshi",
            # old reference fully gone
            "old_in_manifest": False,
            "old_in_lockfile": False,
            "old_content_present": False,
            # new reference present under the inherited role
            "new_in_manifest": True,
            "new_role": "json-mapping",
            "new_resolved": "v1.15.0",
            "new_ref_type": "tag",
            # baseline RESET → owed delta True, nothing confirmed yet
            "new_owed_delta": True,
            "new_confirmed_through_is_none": True,
            # counts unchanged (one out, one in)
            "manifest_count": 1,
            "lockfile_count": 1,
            # agent inventory refreshed and names the new reference
            "inventory_mentions_new": True,
            "inventory_mentions_old": False,
        },
    },
    # Swapping a semver-tracked reference: new reference resolves the highest in-range tag.
    "swap_semver_reference": {
        "input": {
            "role": "spec-driven",
            "old": {"name": "openspec", "source": "acme/openspec", "tag": "v2.1.0"},
            # new reference declares a caret range; v3.2.0 is the highest matching tag.
            "new": {
                "name": "betterspec",
                "source": "acme/betterspec",
                "version": "^3.0.0",
                "available_tags": ["v3.0.0", "v3.2.0", "v4.0.0"],
                "resolves_to": "v3.2.0",
            },
        },
        "expect": {
            "result_role": "spec-driven",
            "result_removed_name": "openspec",
            "result_added_name": "betterspec",
            "old_in_manifest": False,
            "old_in_lockfile": False,
            "new_in_manifest": True,
            "new_role": "spec-driven",
            "new_resolved": "v3.2.0",
            "new_ref_type": "semver",
            "new_owed_delta": True,
            "new_confirmed_through_is_none": True,
            "manifest_count": 1,
            "lockfile_count": 1,
            "inventory_mentions_new": True,
            "inventory_mentions_old": False,
        },
    },
}
