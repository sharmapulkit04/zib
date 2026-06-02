"""Scenario data for the list_references capability (Query).

Each scenario seeds a set of declared references (some pinned, some pending, some
with an owed delta) and asserts the EXACT inventory rows ``zib list`` returns,
in EXACT order (name-sorted). Plain domain constants; concrete expected values.

Seed shape per reference (``seed`` is a list of these dicts):
    name        — RefName value
    role        — Role value
    ref_type    — declared RefKind value (semver/tag/latest/branch/rev)
    spec_value  — RefSpec value (None for latest)
    pinned      — if True, a LockEntry is created
    resolved    — the lock entry's resolved label (when pinned)
    lock_type   — the lock entry's RefKind value (when pinned; defaults to ref_type)
    owed        — when pinned: True advances the pin past the confirmed baseline

``expect.rows`` is the ordered list of (name, role, ref_type, resolved, owed_delta)
the capability must return.
"""

from __future__ import annotations

SCENARIOS = {
    # All pinned, all caught up. Seeded out of order; must come back name-sorted.
    "all_pinned_sorted": {
        "input": {
            "seed": [
                {
                    "name": "style",
                    "role": "code-style",
                    "ref_type": "branch",
                    "spec_value": "main",
                    "pinned": True,
                    "resolved": "main",
                    "owed": False,
                },
                {
                    "name": "api-spec",
                    "role": "json-mapping",
                    "ref_type": "semver",
                    "spec_value": "^2.1.0",
                    "pinned": True,
                    "resolved": "2.1.4",
                    "owed": False,
                },
            ],
        },
        "expect": {
            "count": 2,
            "rows": [
                ("api-spec", "json-mapping", "semver", "2.1.4", False),
                ("style", "code-style", "branch", "main", False),
            ],
        },
    },
    # One reference's pin leads its confirmed baseline -> owed_delta True.
    "owed_delta_flagged": {
        "input": {
            "seed": [
                {
                    "name": "spec",
                    "role": "protocol",
                    "ref_type": "semver",
                    "spec_value": "^1.0.0",
                    "pinned": True,
                    "resolved": "1.3.0",
                    "owed": True,
                },
            ],
        },
        "expect": {
            "count": 1,
            "rows": [
                ("spec", "protocol", "semver", "1.3.0", True),
            ],
        },
    },
    # Declared but not yet installed: appears with declared kind + "not installed".
    "declared_not_installed": {
        "input": {
            "seed": [
                {
                    "name": "guide",
                    "role": "onboarding",
                    "ref_type": "tag",
                    "spec_value": "v3.0.0",
                    "pinned": False,
                },
            ],
        },
        "expect": {
            "count": 1,
            "rows": [
                ("guide", "onboarding", "tag", "not installed", False),
            ],
        },
    },
    # Mixed: a caught-up semver, an owed-delta latest, and a pending tag ref.
    "mixed_states": {
        "input": {
            "seed": [
                {
                    "name": "zeta",
                    "role": "validation",
                    "ref_type": "latest",
                    "spec_value": None,
                    "pinned": True,
                    "resolved": "4.0.0",
                    "lock_type": "semver",
                    "owed": True,
                },
                {
                    "name": "alpha",
                    "role": "schema",
                    "ref_type": "semver",
                    "spec_value": "~1.2.0",
                    "pinned": True,
                    "resolved": "1.2.9",
                    "owed": False,
                },
                {
                    "name": "mid",
                    "role": "examples",
                    "ref_type": "tag",
                    "spec_value": "v0.9.0",
                    "pinned": False,
                },
            ],
        },
        "expect": {
            "count": 3,
            "rows": [
                ("alpha", "schema", "semver", "1.2.9", False),
                ("mid", "examples", "tag", "not installed", False),
                ("zeta", "validation", "semver", "4.0.0", True),
            ],
        },
    },
    # A frozen rev reference: pinned, never owes a delta when confirmed.
    "frozen_rev": {
        "input": {
            "seed": [
                {
                    "name": "pinned-doc",
                    "role": "archive",
                    "ref_type": "rev",
                    "spec_value": "f" * 40,
                    "pinned": True,
                    "resolved": ("f" * 40)[:7],
                    "lock_type": "rev",
                    "owed": False,
                },
            ],
        },
        "expect": {
            "count": 1,
            "rows": [
                ("pinned-doc", "archive", "rev", "fffffff", False),
            ],
        },
    },
}
