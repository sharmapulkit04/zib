"""Persistence ports — simple, direct driven interfaces (no orchestration).

These are ports (not gateways) because reading/writing local files needs no
transformation, rules, or lifecycle — just CRUD. Infrastructure satisfies these by
matching the method signatures (structural typing via Protocol; no inheritance needed).

The one subtlety lives in the *adapter*, not here: writes are canonical and
compare-before-write, so re-running a command that changes nothing rewrites nothing
(idempotency / clean diffs). That's an adapter contract, asserted by the port's
contract test — not a core concern.

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest
from zib.core.entities.shared.value_objects import ContentHash, RefName, TreeEntry


@runtime_checkable
class ManifestStore(Protocol):
    """Reads/writes ``zib.toml``. Write preserves user formatting/comments."""

    def read(self) -> Manifest: ...
    def write(self, manifest: Manifest) -> None: ...
    def exists(self) -> bool: ...


@runtime_checkable
class LockfileStore(Protocol):
    """Reads/writes ``zib.lock`` with canonical, compare-before-write emission."""

    def read(self) -> Lockfile: ...
    def write(self, lockfile: Lockfile) -> None: ...
    def exists(self) -> bool: ...


@runtime_checkable
class ContentStore(Protocol):
    """Materializes and verifies reference content under ``.zib/references/``.

    Each reference's content is stored by name + resolved label, so the agent can read it
    and zib can verify it still hashes to the pin.
    """

    def materialize(self, name: RefName, label: str, tree: list[TreeEntry]) -> None: ...
    def read_tree(self, name: RefName, label: str) -> list[TreeEntry]: ...
    def verify(self, name: RefName, label: str, expected: ContentHash) -> bool: ...
    def remove(self, name: RefName) -> None: ...


@runtime_checkable
class AgentFileStore(Protocol):
    """Maintains the agent-facing files (AGENTS.md marked block, CLAUDE.md import).

    The managed block is rewritten between markers; everything outside the markers is
    preserved verbatim. zib never parses the developer's own prose — it only owns its block.
    """

    def write_inventory_block(self, body: str) -> None: ...
    def ensure_claude_import(self) -> None: ...
