"""Scenario data for the outdated capability — defined once, reused by e2e.

These encode solution spec §8.4's poll states as concrete user journeys (CLAUDE.md:
scenarios are data with CONCRETE expected values, not shapes). Each scenario seeds one
declared reference, its lock entry, and the live tag list (or branch tip), then states the
exact ``drift_status`` / ``target`` / ``owed_delta`` the read-only poll must report.

Domain constants:
  SOURCE              — the repo identifier every reference is declared against.
  PIN_COMMIT          — the commit currently pinned in the lockfile.
  *_COMMIT            — distinct 40-hex shas the fake git port hands back per tag/tip.
  PIN_HASH            — the pinned tree's content hash (any well-formed sha256 value).

The drift_status values are the string forms of ``DriftStatus``:
  "up_to_date" / "update_available" / "upgrade_available".
"""

from __future__ import annotations

SOURCE = "acme/spec"

PIN_COMMIT = "a" * 40
WANTED_COMMIT = "b" * 40   # a newer in-constraint version's commit
LATEST_COMMIT = "c" * 40   # a newer out-of-constraint (next-major) version's commit

PIN_HASH = "sha256:" + ("a" * 64)

SCENARIOS = {
    # In-range update: pinned 2.1.0 under ^2.1.0; 2.1.3 exists and satisfies the
    # constraint. `update` would take it → UPDATE_AVAILABLE, target = the in-range high.
    "in_range_update_available": {
        "input": {
            "spec": {"version": "^2.1.0"},
            "ref_type": "semver",
            "resolved": "2.1.0",
            "confirmed": True,
            "tags": [
                ("2.1.0", PIN_COMMIT),
                ("2.1.3", WANTED_COMMIT),
            ],
        },
        "expect": {
            "drift_status": "update_available",
            "target": "2.1.3",
            "owed_delta": False,
        },
    },
    # Out-of-range upgrade: pinned 2.1.0 under ^2.1.0; the newest in-range is the pin
    # itself, but 3.0.0 exists beyond the caret. Only `upgrade` (rewrites the constraint)
    # can take it → UPGRADE_AVAILABLE, target = the overall high.
    "out_of_range_upgrade_available": {
        "input": {
            "spec": {"version": "^2.1.0"},
            "ref_type": "semver",
            "resolved": "2.1.0",
            "confirmed": True,
            "tags": [
                ("2.1.0", PIN_COMMIT),
                ("3.0.0", LATEST_COMMIT),
            ],
        },
        "expect": {
            "drift_status": "upgrade_available",
            "target": "3.0.0",
            "owed_delta": False,
        },
    },
    # Up to date: pinned 2.1.0 under ^2.1.0 and 2.1.0 is the highest tag. Nothing newer
    # anywhere → UP_TO_DATE, no target, nothing owed.
    "up_to_date": {
        "input": {
            "spec": {"version": "^2.1.0"},
            "ref_type": "semver",
            "resolved": "2.1.0",
            "confirmed": True,
            "tags": [
                ("2.0.0", LATEST_COMMIT),
                ("2.1.0", PIN_COMMIT),
            ],
        },
        "expect": {
            "drift_status": "up_to_date",
            "target": None,
            "owed_delta": False,
        },
    },
    # Owed delta: the pin leads the confirmed baseline (confirmed < pin), so even when the
    # ref is fully up to date upstream, the agent still owes a confirm → owed_delta True.
    "owed_delta_when_confirmed_behind_pin": {
        "input": {
            "spec": {"version": "^2.1.0"},
            "ref_type": "semver",
            "resolved": "2.1.0",
            "confirmed": False,   # confirmed_through left as a prior commit, behind the pin
            "tags": [
                ("2.1.0", PIN_COMMIT),
            ],
        },
        "expect": {
            "drift_status": "up_to_date",
            "target": None,
            "owed_delta": True,
        },
    },
}
