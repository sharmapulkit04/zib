"""init capability (Command) — scaffold a fresh zib workspace.

User intent: "the user wants to start managing references in this project." This is the
very first command run. It lays down an empty manifest (``zib.toml``), wires the agent
files so an AI agent will read zib's managed block (the ``@AGENTS.md`` import in
``CLAUDE.md``), and writes the initial — empty — inventory block the agent reads.

It is a pure orchestrator (CLAUDE.md):
    mutate entities          -> build an empty Manifest
    persist                  -> manifest_store.write(...)
    update agent files LAST  -> agent_file_store.ensure_claude_import() + write_inventory_block(...)

The inventory body is produced by the real ``render_inventory`` rule with an empty item
list, so the "no references yet" block the agent reads is identical to what every later
command renders — one source of truth, deterministic and dumb.

Idempotent: if a manifest already exists this is a no-op (``created=False``). Re-running
``zib init`` never clobbers an existing workspace.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.manifest.manifest import Manifest
from zib.core.ports.persistence.stores import AgentFileStore, ManifestStore
from zib.core.rules.computation.inventory.render_inventory import render_inventory


@dataclass(frozen=True, slots=True)
class InitResult:
    """Outcome of ``zib init``.

    ``created`` is True when this call scaffolded a fresh workspace, False when a manifest
    already existed and the call was an idempotent no-op.
    """

    created: bool


class InitCapability:
    """Scaffold an empty zib workspace. Idempotent."""

    def __init__(self, manifest_store: ManifestStore, agent_file_store: AgentFileStore) -> None:
        self._manifest_store = manifest_store
        self._agent_file_store = agent_file_store

    def execute(self) -> InitResult:
        # Idempotent: an existing workspace is left untouched.
        if self._manifest_store.exists():
            return InitResult(created=False)

        # mutate entities: a fresh, empty declared-intent manifest.
        manifest = Manifest()

        # persist first (CLAUDE.md ordering for state-changers).
        self._manifest_store.write(manifest)

        # update agent files LAST: wire the CLAUDE.md import, then write the empty
        # inventory block via the real rule so the agent reads the canonical body.
        self._agent_file_store.ensure_claude_import()
        self._agent_file_store.write_inventory_block(render_inventory([]))

        return InitResult(created=True)
