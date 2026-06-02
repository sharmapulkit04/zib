"""Scenario data for the show_reference capability (Query).

Plain domain constants in, concrete expected RefDetail fields out. The seed describes
the manifest declaration and, optionally, the lockfile pin for one reference; the test
builds the stores from it, runs ``ShowReference.execute(show)``, and asserts each field
exactly. Reused by the e2e layer later.

Seed keys:
    name, role, source            — manifest declaration
    version/branch/tag/rev        — exactly one, collapsed via RefSpec.from_manifest
    subdirectory, description     — optional manifest fields (None if absent)
    lock                          — optional dict {resolved, commit, confirmed} or absent
                                    (absent = declared but not installed)
"""

from __future__ import annotations

_SPEC_COMMIT = "a" * 40
_STYLE_COMMIT = "b" * 40
_OLD_COMMIT = "c" * 40
_HASH = "sha256:" + "1" * 64

SCENARIOS = {
    # Fully installed semver reference, caught up (confirmed == pin).
    "installed_semver_caught_up": {
        "input": {
            "seed": {
                "name": "spec",
                "role": "json-mapping",
                "source": "acme/spec",
                "version": "^2.1.0",
                "subdirectory": "docs",
                "description": "the mapping spec",
                "lock": {
                    "resolved": "2.1.4",
                    "commit": _SPEC_COMMIT,
                    "confirmed": _SPEC_COMMIT,
                },
            },
            "show": "spec",
        },
        "expect": {
            "name": "spec",
            "role": "json-mapping",
            "source": "acme/spec",
            "spec_repr": "version ^2.1.0",
            "resolved": "2.1.4",
            "pinned_commit": _SPEC_COMMIT,
            "confirmed_commit": _SPEC_COMMIT,
            "subdirectory": "docs",
            "description": "the mapping spec",
        },
    },
    # Installed but the pin leads the confirmed baseline — an owed delta is visible
    # as confirmed_commit != pinned_commit.
    "installed_owed_delta": {
        "input": {
            "seed": {
                "name": "spec",
                "role": "json-mapping",
                "source": "acme/spec",
                "version": "^2.1.0",
                "subdirectory": None,
                "description": None,
                "lock": {
                    "resolved": "2.1.4",
                    "commit": _SPEC_COMMIT,
                    "confirmed": _OLD_COMMIT,
                },
            },
            "show": "spec",
        },
        "expect": {
            "name": "spec",
            "role": "json-mapping",
            "source": "acme/spec",
            "spec_repr": "version ^2.1.0",
            "resolved": "2.1.4",
            "pinned_commit": _SPEC_COMMIT,
            "confirmed_commit": _OLD_COMMIT,
            "subdirectory": None,
            "description": None,
        },
    },
    # Installed but never confirmed — confirmed_commit is None.
    "installed_never_confirmed": {
        "input": {
            "seed": {
                "name": "style",
                "role": "code-style",
                "source": "acme/style",
                "tag": "v3.0.0",
                "subdirectory": None,
                "description": "house style",
                "lock": {
                    "resolved": "v3.0.0",
                    "commit": _STYLE_COMMIT,
                    "confirmed": None,
                },
            },
            "show": "style",
        },
        "expect": {
            "name": "style",
            "role": "code-style",
            "source": "acme/style",
            "spec_repr": "tag v3.0.0",
            "resolved": "v3.0.0",
            "pinned_commit": _STYLE_COMMIT,
            "confirmed_commit": None,
            "subdirectory": None,
            "description": "house style",
        },
    },
    # Branch-tracked reference.
    "installed_branch": {
        "input": {
            "seed": {
                "name": "guide",
                "role": "how-to",
                "source": "https://git.acme.dev/team/guide.git",
                "branch": "main",
                "subdirectory": None,
                "description": None,
                "lock": {
                    "resolved": "main",
                    "commit": _STYLE_COMMIT,
                    "confirmed": _STYLE_COMMIT,
                },
            },
            "show": "guide",
        },
        "expect": {
            "name": "guide",
            "role": "how-to",
            "source": "https://git.acme.dev/team/guide.git",
            "spec_repr": "branch main",
            "resolved": "main",
            "pinned_commit": _STYLE_COMMIT,
            "confirmed_commit": _STYLE_COMMIT,
            "subdirectory": None,
            "description": None,
        },
    },
    # Frozen rev reference.
    "installed_rev": {
        "input": {
            "seed": {
                "name": "frozen",
                "role": "snapshot",
                "source": "acme/frozen",
                "rev": _OLD_COMMIT,
                "subdirectory": "sub/dir",
                "description": None,
                "lock": {
                    "resolved": _OLD_COMMIT[:7],
                    "commit": _OLD_COMMIT,
                    "confirmed": _OLD_COMMIT,
                },
            },
            "show": "frozen",
        },
        "expect": {
            "name": "frozen",
            "role": "snapshot",
            "source": "acme/frozen",
            "spec_repr": f"rev {_OLD_COMMIT}",
            "resolved": _OLD_COMMIT[:7],
            "pinned_commit": _OLD_COMMIT,
            "confirmed_commit": _OLD_COMMIT,
            "subdirectory": "sub/dir",
            "description": None,
        },
    },
    # LATEST-tracked reference.
    "installed_latest": {
        "input": {
            "seed": {
                "name": "spec",
                "role": "json-mapping",
                "source": "acme/spec",
                "version": "latest",
                "subdirectory": None,
                "description": None,
                "lock": {
                    "resolved": "2.1.4",
                    "commit": _SPEC_COMMIT,
                    "confirmed": _SPEC_COMMIT,
                },
            },
            "show": "spec",
        },
        "expect": {
            "name": "spec",
            "role": "json-mapping",
            "source": "acme/spec",
            "spec_repr": "version latest",
            "resolved": "2.1.4",
            "pinned_commit": _SPEC_COMMIT,
            "confirmed_commit": _SPEC_COMMIT,
            "subdirectory": None,
            "description": None,
        },
    },
    # Declared but not yet installed — manifest only, no lock entry.
    "declared_not_installed": {
        "input": {
            "seed": {
                "name": "spec",
                "role": "json-mapping",
                "source": "acme/spec",
                "version": "^2.1.0",
                "subdirectory": "docs",
                "description": "the mapping spec",
                "lock": None,
            },
            "show": "spec",
        },
        "expect": {
            "name": "spec",
            "role": "json-mapping",
            "source": "acme/spec",
            "spec_repr": "version ^2.1.0",
            "resolved": "not installed",
            "pinned_commit": "not installed",
            "confirmed_commit": None,
            "subdirectory": "docs",
            "description": "the mapping spec",
        },
    },
}
