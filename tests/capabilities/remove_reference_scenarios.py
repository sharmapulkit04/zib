"""Scenario data for the remove_reference capability.

Plain domain constants, concrete expectations. Reused by the capability test now and
the e2e shell test later (CLAUDE.md: scenarios defined once, run at two levels).

Each scenario seeds a manifest+lockfile+content set, asks to remove one name, and
asserts the concrete surviving state across all three stores plus the rebuilt block.
"""

from __future__ import annotations

# Reference names present before removal in the multi-reference scenarios.
SPEC = "spec"
STYLE = "style"

SCENARIOS = {
    # Removing one of two references clears exactly that one, everywhere.
    "remove_one_of_two": {
        "input": {
            "seed": [SPEC, STYLE],
            "remove": SPEC,
        },
        "expect": {
            "result_name": SPEC,
            "manifest_has": [STYLE],
            "manifest_missing": [SPEC],
            "lock_len": 1,
            "lock_has": [STYLE],
            "lock_missing": [SPEC],
            # content for the removed name is gone; the survivor's content stays.
            "content_present": {SPEC: False, STYLE: True},
            # block was refreshed and no longer names the removed reference.
            "block_mentions": [STYLE],
            "block_omits": [SPEC],
        },
    },
    # Removing the only reference leaves everything empty and an empty-body block.
    "remove_last_one": {
        "input": {
            "seed": [SPEC],
            "remove": SPEC,
        },
        "expect": {
            "result_name": SPEC,
            "manifest_has": [],
            "manifest_missing": [SPEC],
            "lock_len": 0,
            "lock_has": [],
            "lock_missing": [SPEC],
            "content_present": {SPEC: False},
            "block_mentions": [],
            "block_omits": [SPEC],
        },
    },
}
