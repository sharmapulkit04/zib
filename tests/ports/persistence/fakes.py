"""In-memory test doubles for the persistence ports.

Each fake satisfies the corresponding ``zib.core.ports.persistence.stores`` Protocol by
structural typing — it just matches the method signatures. They are validated by
``test_store_contracts.py`` before any test above is allowed to trust them
(CLAUDE.md: every fake passes its contract test first).

Design choices (documented per the assignment):
  * ``FakeManifestStore`` / ``FakeLockfileStore`` start empty. ``read()`` before any
    ``write()`` returns a *fresh empty aggregate* (empty Manifest / default Lockfile);
    ``exists()`` returns False until the first ``write()`` and True afterwards.
  * Stored aggregates are returned directly (the same object that was written), so a
    write-then-read round trip yields an EQUAL aggregate.
  * ``FakeContentStore`` keys trees by ``(name, label)`` and recomputes the content hash
    via the real ``compute_content_hash`` rule in ``verify()``.
  * ``FakeAgentFileStore`` records the last managed-block body and whether the CLAUDE.md
    import was ensured.

No side effects at import time — importable by any other test module.
"""

from __future__ import annotations

from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest
from zib.core.entities.shared.value_objects import ContentHash, RefName, TreeEntry
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash


class FakeManifestStore:
    """In-memory ``ManifestStore``. Starts empty; ``read()`` returns a fresh Manifest."""

    def __init__(self) -> None:
        self._manifest: Manifest | None = None

    def read(self) -> Manifest:
        if self._manifest is None:
            return Manifest()
        return self._manifest

    def write(self, manifest: Manifest) -> None:
        self._manifest = manifest

    def exists(self) -> bool:
        return self._manifest is not None


class FakeLockfileStore:
    """In-memory ``LockfileStore``. Starts empty; ``read()`` returns a default Lockfile."""

    def __init__(self) -> None:
        self._lockfile: Lockfile | None = None

    def read(self) -> Lockfile:
        if self._lockfile is None:
            return Lockfile()
        return self._lockfile

    def write(self, lockfile: Lockfile) -> None:
        self._lockfile = lockfile

    def exists(self) -> bool:
        return self._lockfile is not None


class FakeContentStore:
    """In-memory ``ContentStore`` keyed by ``(name, label)``.

    ``verify()`` recomputes the canonical hash from the stored tree via the real rule and
    compares it to ``expected`` — exactly what a real adapter must do on disk.
    """

    def __init__(self) -> None:
        self._trees: dict[tuple[str, str], list[TreeEntry]] = {}

    def materialize(self, name: RefName, label: str, tree: list[TreeEntry]) -> None:
        self._trees[(str(name), label)] = list(tree)

    def read_tree(self, name: RefName, label: str) -> list[TreeEntry]:
        return list(self._trees[(str(name), label)])

    def verify(self, name: RefName, label: str, expected: ContentHash) -> bool:
        tree = self._trees.get((str(name), label))
        if tree is None:
            return False
        return compute_content_hash(tree) == expected

    def remove(self, name: RefName) -> None:
        key_name = str(name)
        for key in [k for k in self._trees if k[0] == key_name]:
            del self._trees[key]


class FakeAgentFileStore:
    """In-memory ``AgentFileStore``. Records the last block body and the import flag."""

    def __init__(self) -> None:
        self.last_block: str | None = None
        self.claude_imported: bool = False

    def write_inventory_block(self, body: str) -> None:
        self.last_block = body

    def ensure_claude_import(self) -> None:
        self.claude_imported = True
