"""Scenario data for the ``init`` capability — defined once, reused by e2e later.

Plain domain constants, concrete expected values. ``preexisting`` says whether a manifest
is already present before ``execute()`` runs; the expectations assert the exact post-state
of the workspace (created flag + persisted manifest + agent-file side effects).
"""

from __future__ import annotations

# The exact body the real render_inventory rule emits for an empty workspace. Asserting the
# literal text proves the agent reads the canonical "no references yet" block after init.
EMPTY_INVENTORY_BODY = (
    "## Managed references (zib)\n"
    "\n"
    "No references are pinned yet. Run `zib add <name> --role <role> --git <repo>` to add one."
)

SCENARIOS = {
    "fresh_project": {
        "input": {"preexisting": False},
        "expect": {
            "created": True,
            "manifest_exists": True,
            "manifest_reference_count": 0,
            "claude_imported": True,
            "inventory_block": EMPTY_INVENTORY_BODY,
        },
    },
    "already_initialized": {
        "input": {"preexisting": True},
        "expect": {
            "created": False,
            "manifest_exists": True,
            "manifest_reference_count": 0,
            # No agent-file work happens on the idempotent no-op path.
            "claude_imported": False,
            "inventory_block": None,
        },
    },
}
