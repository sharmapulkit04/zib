"""Scenario data for the add_reference capability — defined once, reused by e2e later.

Each scenario is a real user journey expressed in plain domain constants, with CONCRETE
expected outcomes (exact labels, commits, owed-delta booleans). The capability test and a
future shell e2e test run the SAME scenarios at different execution depths (CLAUDE.md:
scenarios assert concrete values; the breakage is the impact signal).

Git fixtures are described declaratively so any harness (FakeGitPort here, a real repo in
e2e) can be set up identically:
  * ``tags``     — list of (tag name, 40-hex commit) registered on the source.
  * ``branches`` — list of (branch name, 40-hex commit) registered on the source.
  * ``trees``    — {commit hex: [(path, mode, blob bytes)]} exported at each commit.

The ``input`` carries the manifest-level coordinates the capability receives; ``ref_kind``
+ ``ref_value`` collapse into the RefSpec the test builds via RefSpec.from_manifest.
"""

from __future__ import annotations

# Distinct 40-hex commit SHAs used across scenarios.
COMMIT_210 = "a" * 40
COMMIT_213 = "b" * 40
COMMIT_220 = "c" * 40
COMMIT_MAIN = "d" * 40

SOURCE = "acme/spec"


SCENARIOS = {
    # Semver range ^2.1.0 over tags {2.1.0, 2.1.3, 2.2.0} -> highest IN range is 2.1.3
    # (2.2.0 is outside ^2.1.0 which is >=2.1.0 <3.0.0... wait caret allows it).
    # ^2.1.0 == >=2.1.0 <3.0.0, so the highest satisfying is 2.2.0.
    "add_semver_picks_highest_in_range": {
        "input": {
            "name": "spec",
            "role": "json-mapping",
            "source": SOURCE,
            "ref_kind": "version",
            "ref_value": "^2.1.0",
            "description": "the canonical JSON mapping spec",
            "subdirectory": None,
        },
        "fixtures": {
            "tags": [
                ("2.1.0", COMMIT_210),
                ("2.1.3", COMMIT_213),
                ("2.2.0", COMMIT_220),
            ],
            "branches": [],
            "trees": {
                COMMIT_220: [("spec.md", 0o100644, b"# JSON mapping v2.2.0\n")],
            },
        },
        "expect": {
            "resolved_label": "2.2.0",
            "commit": COMMIT_220,
            "ref_type": "semver",
            "manifest_count": 1,
            "lock_count": 1,
            "owed_delta": True,           # confirmed_through None on a fresh add
            "content_verifies": True,
            "claude_imported": False,     # add does not touch the CLAUDE.md import
            "block_contains": "spec · json-mapping",
            "block_contains_pending": True,
        },
    },
    # Branch tracking: pins the current tip, label is the branch name, ref_type BRANCH.
    "add_branch_pins_tip": {
        "input": {
            "name": "guide",
            "role": "style-guide",
            "source": SOURCE,
            "ref_kind": "branch",
            "ref_value": "main",
            "description": None,
            "subdirectory": None,
        },
        "fixtures": {
            "tags": [],
            "branches": [("main", COMMIT_MAIN)],
            "trees": {
                COMMIT_MAIN: [("guide.md", 0o100644, b"# Style guide (main)\n")],
            },
        },
        "expect": {
            "resolved_label": "main",
            "commit": COMMIT_MAIN,
            "ref_type": "branch",
            "manifest_count": 1,
            "lock_count": 1,
            "owed_delta": True,
            "content_verifies": True,
            "claude_imported": False,
            "block_contains": "guide · style-guide",
            "block_contains_pending": True,
        },
    },
    # Duplicate name: a reference already declared -> ValueError, nothing else changes.
    "add_duplicate_name_errors": {
        "input": {
            "name": "spec",
            "role": "json-mapping",
            "source": SOURCE,
            "ref_kind": "version",
            "ref_value": "^2.1.0",
            "description": None,
            "subdirectory": None,
        },
        "fixtures": {
            "tags": [("2.1.0", COMMIT_210)],
            "branches": [],
            "trees": {
                COMMIT_210: [("spec.md", 0o100644, b"# v2.1.0\n")],
            },
        },
        "preexisting": {
            "name": "spec",
            "role": "json-mapping",
            "source": SOURCE,
            "ref_kind": "version",
            "ref_value": "^2.1.0",
        },
        "expect": {
            "error": "already exists",
        },
    },
}
