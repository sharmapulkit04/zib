"""Scenario data for the read_reference capability (``zib cat <name>``).

Defined once here as plain domain constants with CONCRETE expected values, run by
``test_read_reference.py`` with real aggregates + fake stores, and reused later by the
shell e2e suite. The agent's read returns the materialized tree of the *pinned*
reference, keyed by the lock entry's ``resolved`` label.

Seed shape per reference name:
  * ``role`` / ``source`` declared in the manifest
  * a ``spec`` (the declared lane — may be a range; never the on-disk key)
  * a pin at ``resolved`` (the on-disk label) materialized with a concrete tree
"""

from __future__ import annotations

# Each reference: (role, declared spec value, resolved label, tree files as
# (path, text)). The tree text is what the agent must read back verbatim.
_SPEC_TREE = [("spec.md", "the json mapping spec\n"), ("examples.md", "ex\n")]
_STYLE_TREE = [("style.md", "two-space indent\n")]
_GUIDE_TREE = [("guide.md", "branch-tracked guide\n")]

SEED = {
    "spec": {
        "role": "json-mapping",
        "spec_value": "^2.1.0",
        "resolved": "2.1.4",
        "tree": _SPEC_TREE,
    },
    "style": {
        "role": "code-style",
        "spec_value": "~1.0.0",
        "resolved": "1.0.3",
        "tree": _STYLE_TREE,
    },
    "guide": {
        "role": "house-guide",
        "spec_value": "main",  # branch lane
        "resolved": "main@9f8e7d6",
        "tree": _GUIDE_TREE,
    },
}

SCENARIOS = {
    # Reads the chosen reference's materialized tree at its resolved label.
    "reads_pinned_spec": {
        "input": {"seed": ["spec", "style"], "read": "spec"},
        "expect": {
            "file_count": 2,
            "paths": ["spec.md", "examples.md"],
            "blobs": {
                "spec.md": b"the json mapping spec\n",
                "examples.md": b"ex\n",
            },
        },
    },
    # A second reference in the same project reads back its own bytes, not the spec's.
    "reads_other_reference_independently": {
        "input": {"seed": ["spec", "style"], "read": "style"},
        "expect": {
            "file_count": 1,
            "paths": ["style.md"],
            "blobs": {"style.md": b"two-space indent\n"},
        },
    },
    # A branch-tracked reference reads through its branch@sha resolved label.
    "reads_branch_tracked_reference": {
        "input": {"seed": ["guide"], "read": "guide"},
        "expect": {
            "file_count": 1,
            "paths": ["guide.md"],
            "blobs": {"guide.md": b"branch-tracked guide\n"},
        },
    },
}
