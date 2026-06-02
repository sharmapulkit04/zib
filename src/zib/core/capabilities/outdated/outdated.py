"""outdated — the read-only freshness poll. (Query)

This is solution spec §8.4's ``zib outdated``: a stateless, **read-only** poll that, for
each declared reference, reports where the locked pin sits relative to what's available
upstream, plus whether the agent still owes a delta (the pin leads the confirmed baseline,
§9.3). It mutates nothing — no fetch, no write — and the CLI exits 0 regardless of findings
(the ``--exit-code`` opt-in is a shell concern, not this capability's).

It is a pure orchestrator (CLAUDE.md: a capability contains no business logic itself):

  * SEMVER / LATEST — delegate to the ``assess_drift`` rule against the live tag list.
    The rule decides ``UP_TO_DATE`` / ``UPDATE_AVAILABLE`` (newer in-range → ``update``) /
    ``UPGRADE_AVAILABLE`` (newer only out-of-range → ``upgrade``) and the target version.
  * BRANCH — a tracking ref: re-resolve the branch tip and compare to the pinned commit.
    Tip moved → ``UPDATE_AVAILABLE`` (``update`` advances it); otherwise ``UP_TO_DATE``.
    The branch is always-newest, so there is no out-of-range "upgrade" notion for it.
  * REV — a frozen commit: never moves, so always ``UP_TO_DATE`` (no tag list consulted).
  * TAG — a literal release tag taken as-is (no semver interpretation), so this poll has no
    version lane to compare against; reported ``UP_TO_DATE`` here. (Constraint drift for a
    literal tag is install's concern, not this read-only poll's.)

``owed_delta`` is read straight off the lock entry's own data (``has_owed_delta()``): the
pin ahead of the confirmed baseline is the "pending-confirm" signal of §8.4 — orthogonal to
upstream drift (a ref can be fully up-to-date upstream yet still owe a confirm).

The reported ``drift_status`` is the rule's status value (``DriftStatus.value``) so the
shell can render it without importing the rule's enum.

Pure stdlib + zib.core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.shared.value_objects import RefKind, RefName
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.ports.persistence.stores import LockfileStore, ManifestStore
from zib.core.rules.validation.constraint_drift.constraint_drift import (
    DriftStatus,
    assess_drift,
)


@dataclass(frozen=True, slots=True)
class OutdatedItem:
    """One reference's poll line: where it sits upstream + whether a confirm is owed.

    ``drift_status`` is the string value of :class:`DriftStatus`
    (``"up_to_date"`` / ``"update_available"`` / ``"upgrade_available"``). ``target`` is the
    version ``update``/``upgrade`` would move to, or ``None`` when nothing newer applies
    (and always ``None`` for branch/rev/tag, which have no version target). ``owed_delta``
    is the pin-ahead-of-confirmed signal — independent of upstream drift.
    """

    name: str
    drift_status: str
    target: str | None
    owed_delta: bool


class Outdated:
    """Poll every declared reference (read-only) and report drift + owed delta."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        git_port: GitPort,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._git_port = git_port

    def execute(self) -> list[OutdatedItem]:
        manifest = self._manifest_store.read()
        lockfile = self._lockfile_store.read()

        items: list[OutdatedItem] = []
        for reference in manifest.references:
            entry = lockfile.get(reference.name)
            if entry is None:
                # Declared but not yet installed/pinned: nothing to poll against. A
                # missing pin is install's job to surface, not this read-only drift poll.
                continue

            status, target = self._assess(reference, entry)
            items.append(
                OutdatedItem(
                    name=str(reference.name),
                    drift_status=status.value,
                    target=target,
                    owed_delta=entry.has_owed_delta(),
                )
            )
        return items

    def _assess(self, reference, entry) -> tuple[DriftStatus, str | None]:
        """Map one reference's ref kind to a drift verdict (status, target)."""
        kind = entry.ref_type

        if kind in (RefKind.SEMVER, RefKind.LATEST):
            tags = self._git_port.list_tags(reference.source)
            result = assess_drift(reference.spec, entry.resolved, tags)
            return result.status, result.target

        if kind is RefKind.BRANCH:
            # Tracking mode: the branch tip is always-newest. Re-resolve and compare to the
            # pinned commit; a moved tip is an in-range update (`update` advances it).
            branch = reference.spec.value or entry.resolved
            tip = self._git_port.resolve(reference.source, branch)
            if tip != entry.pin.commit:
                return DriftStatus.UPDATE_AVAILABLE, None
            return DriftStatus.UP_TO_DATE, None

        # REV (frozen) and TAG (literal, not version-resolved) never drift in this poll.
        return DriftStatus.UP_TO_DATE, None
