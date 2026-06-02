"""install capability — materialize all manifest references at their locked pins.

`zib install` is the reproducibility verb (solution spec §7, §15.2/§15.9). It walks
the declared references and, for each, reconciles three persisted artifacts — the
manifest's *declared intent*, the lockfile's *pinned reality*, and the content store's
*materialized bytes* — to the state the lockfile records, fetching from git only when it
has to:

    no lock entry                         -> resolve + fetch + lock + materialize   (installed)
    locked, content missing OR hash fails -> re-fetch + re-materialize              (verified)
    locked, materialized, hash verifies   -> verify-only no-op                      (—)

This is a Command (it can change the lockfile and the content store), but a clean install
is a *verify-only no-op*: when nothing needed fetching, the lockfile is not rewritten
(idempotency — solution spec §10). The fetch is always by the immutable ``resolved_commit``
recorded in the lock, never by a re-resolved tag/branch label — install never moves a pin
(that is ``update``/``upgrade``'s job, §10 pin-move invariant). A first encounter (no lock
entry) is the one case install resolves the spec, because there is no pin yet.

Orchestration only — no business logic lives here. It calls the resolve/fetch gateway
processes, the entities' behavioral methods, the persistence ports, and finally the agent
file store. Ordering follows CLAUDE.md for a state-changer:

    mutate entities  ->  persist (manifest / lock / content)  ->  update agent files LAST

Pure stdlib + core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from zib.core.entities.lockfile.lock_entry import LockEntry, Pin
from zib.core.entities.lockfile.lockfile import Lockfile
from zib.core.entities.manifest.manifest import Manifest, ReferenceEntry
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.core.ports.persistence.stores import (
    AgentFileStore,
    ContentStore,
    LockfileStore,
    ManifestStore,
)
from zib.core.rules.computation.inventory.render_inventory import (
    InventoryItem,
    render_inventory,
)


@dataclass(frozen=True, slots=True)
class InstallResult:
    """The outcome of an install run, in domain terms.

    ``installed`` — references that had no lock entry and were resolved, fetched, locked,
    and materialized for the first time (their names, sorted for a stable result).
    ``verified`` — references already locked whose content was missing or failed its hash
    and was re-fetched + re-materialized. References that were already present and verified
    cleanly appear in *neither* list (the verify-only no-op).
    """

    installed: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)


class Install:
    """Install all manifest references at their locked commits; verify hashes; idempotent."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        content_store: ContentStore,
        agent_file_store: AgentFileStore,
        resolve_process: ResolveProcess,
        fetch_process: FetchProcess,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._content_store = content_store
        self._agent_file_store = agent_file_store
        self._resolve = resolve_process
        self._fetch = fetch_process

    def execute(self) -> InstallResult:
        """Reconcile every declared reference to its locked pin; fetch only when needed.

        Returns an :class:`InstallResult` naming what was first-installed vs re-materialized.
        Persists the lockfile only if an entry was added (a clean run rewrites nothing), then
        refreshes zib's managed inventory block last.
        """
        manifest = self._manifest_store.read()
        lockfile = self._lockfile_store.read()

        installed: list[str] = []
        verified: list[str] = []
        lockfile_changed = False

        for entry in manifest.references:
            locked = lockfile.get(entry.name)
            if locked is None:
                # First encounter: no pin exists yet, so resolve the spec, fetch, lock.
                self._first_install(entry, lockfile)
                installed.append(str(entry.name))
                lockfile_changed = True
            elif self._needs_rematerialize(entry, locked):
                # Pinned already; content missing or corrupt -> refetch by the pinned commit.
                self._rematerialize(entry, locked)
                verified.append(str(entry.name))
            # else: present + hash verifies -> verify-only no-op (no rewrite).

        # Persist before touching agent files. A clean run added nothing, so it does not
        # rewrite the lockfile (idempotency — §10); the manifest is never mutated by install.
        if lockfile_changed:
            self._lockfile_store.write(lockfile)

        self._refresh_agent_files(manifest, lockfile)

        return InstallResult(
            installed=sorted(installed), verified=sorted(verified)
        )

    # ------------------------------------------------------------------ helpers

    def _first_install(self, entry: ReferenceEntry, lockfile: Lockfile) -> None:
        """Resolve + fetch a never-locked reference and record its pin + materialize it."""
        resolved = self._resolve.resolve(entry.source, entry.spec)
        fetched = self._fetch.fetch(entry.source, resolved.commit, entry.subdirectory)
        pin = Pin(commit=resolved.commit, content_hash=fetched.content_hash)
        lock_entry = LockEntry(
            name=entry.name,
            ref_type=resolved.ref_type,
            resolved=resolved.label,
            pin=pin,
        )
        lockfile.put(lock_entry)
        self._content_store.materialize(entry.name, resolved.label, fetched.tree)

    def _needs_rematerialize(self, entry: ReferenceEntry, locked: LockEntry) -> bool:
        """True when the locked content is missing or fails its recorded hash.

        ``ContentStore.verify`` returns False both when the tree is absent and when it
        hashes to something other than the pin — exactly the two cases that warrant a
        refetch by commit (solution spec §7).
        """
        return not self._content_store.verify(
            entry.name, locked.resolved, locked.pin.content_hash
        )

    def _rematerialize(self, entry: ReferenceEntry, locked: LockEntry) -> None:
        """Refetch by the *pinned commit* (never re-resolving the label) and re-materialize.

        install never moves a pin (§10 pin-move invariant), so it fetches the exact
        ``resolved_commit`` from the lock — reproducible on any host where that commit is
        reachable. For a BRANCH-tracked reference that reachability is not guaranteed: a
        force-push/rebase upstream can orphan the pinned commit, so this re-fetch can fail
        even though the originally materialized content survives in the project's own VCS
        (decisions.md DS5 — prefer tags for references that must stay reproducible). The
        lockfile is unchanged by this path; only the content store is.
        """
        fetched = self._fetch.fetch(
            entry.source, locked.pin.commit, entry.subdirectory
        )
        self._content_store.materialize(entry.name, locked.resolved, fetched.tree)

    def _refresh_agent_files(self, manifest: Manifest, lockfile: Lockfile) -> None:
        """Rewrite the managed inventory block and ensure the CLAUDE.md import (done last).

        The inventory is built from the manifest (role + description) joined to the lockfile
        (resolved label, ref_type, owed-delta flag) by reference name. References not yet
        locked are skipped — there is nothing pinned to show for them.
        """
        items: list[InventoryItem] = []
        for entry in manifest.references:
            locked = lockfile.get(entry.name)
            if locked is None:
                continue
            items.append(
                InventoryItem(
                    name=str(entry.name),
                    role=str(entry.role),
                    ref_type=locked.ref_type.value,
                    resolved=locked.resolved,
                    description=entry.description,
                    owed_delta=locked.has_owed_delta(),
                )
            )
        self._agent_file_store.write_inventory_block(render_inventory(items))
        self._agent_file_store.ensure_claude_import()
