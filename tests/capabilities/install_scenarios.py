"""Scenario data for the ``install`` capability — defined once, run at every level.

These are real user journeys for ``zib install`` expressed as plain domain constants and
CONCRETE expected outcomes (exact names, exact list contents, exact booleans). The capability
test wires them through the real resolve/fetch gateway processes + a FakeGitPort + fake
stores; an e2e test later reuses the SAME scenarios through the real shell + infrastructure.
The inputs name git sources, tags, and tree files; the expectations name exactly what install
should report and persist.

Each scenario:
  input:
    references — list of declared references (name, role, source, version/branch/tag, files)
    git        — what the fake git remote knows (tags -> commit, tree at each commit)
    pre        — optional prior state to set up before execute() (lockfile entries, whether
                 content was materialized). Absent = a clean first install.
  expect:
    installed  — names first-installed this run (sorted)
    verified   — names re-materialized this run (sorted)
    locked     — per-name resolved label that must end up in the lockfile
    materialized — per-name whether content verifies after the run (always True for a
                 successful install)
"""

from __future__ import annotations

# --- domain constants (stable vocabulary the team agrees on) ----------------------------

SPEC_SRC = "acme/spec"
MAP_SRC = "acme/mapping"

SPEC_V1_COMMIT = "a" * 40
MAP_V1_COMMIT = "b" * 40

SPEC_FILES = [("spec.md", b"# Spec v2.1.0\nrules\n")]
MAP_FILES = [("mapping.md", b"# Mapping v7.4.0\nfields\n")]


SCENARIOS = {
    # Fresh two-reference manifest: both resolved, locked, materialized, both reported installed.
    "fresh_two_refs": {
        "input": {
            "references": [
                {
                    "name": "spec",
                    "role": "spec-driven-development",
                    "source": SPEC_SRC,
                    "version": "^2.1.0",
                    "tags": [("v2.1.0", SPEC_V1_COMMIT)],
                    "tree": {SPEC_V1_COMMIT: SPEC_FILES},
                },
                {
                    "name": "mapping",
                    "role": "json-mapping",
                    "source": MAP_SRC,
                    "tag": "v7.4.0",
                    "tags": [("v7.4.0", MAP_V1_COMMIT)],
                    "tree": {MAP_V1_COMMIT: MAP_FILES},
                },
            ],
        },
        "expect": {
            "installed": ["mapping", "spec"],
            "verified": [],
            "locked": {"spec": "v2.1.0", "mapping": "v7.4.0"},
            "materialized": {"spec": True, "mapping": True},
        },
    },
    # Install again over an already-complete state: nothing resolved, fetched, or changed.
    "idempotent_noop": {
        "input": {
            "references": [
                {
                    "name": "spec",
                    "role": "spec-driven-development",
                    "source": SPEC_SRC,
                    "version": "^2.1.0",
                    "tags": [("v2.1.0", SPEC_V1_COMMIT)],
                    "tree": {SPEC_V1_COMMIT: SPEC_FILES},
                },
            ],
            "pre": {
                # Already locked + materialized before this run.
                "locked": [{"name": "spec", "label": "v2.1.0", "commit": SPEC_V1_COMMIT}],
                "materialized": ["spec"],
            },
        },
        "expect": {
            "installed": [],
            "verified": [],
            "locked": {"spec": "v2.1.0"},
            "materialized": {"spec": True},
        },
    },
    # Locked but content is missing: re-materialize by the pinned commit (verified path).
    "rematerialize_missing": {
        "input": {
            "references": [
                {
                    "name": "spec",
                    "role": "spec-driven-development",
                    "source": SPEC_SRC,
                    "version": "^2.1.0",
                    "tags": [("v2.1.0", SPEC_V1_COMMIT)],
                    "tree": {SPEC_V1_COMMIT: SPEC_FILES},
                },
            ],
            "pre": {
                # Locked, but the content store has nothing on disk for it.
                "locked": [{"name": "spec", "label": "v2.1.0", "commit": SPEC_V1_COMMIT}],
                "materialized": [],
            },
        },
        "expect": {
            "installed": [],
            "verified": ["spec"],
            "locked": {"spec": "v2.1.0"},
            "materialized": {"spec": True},
        },
    },
}
