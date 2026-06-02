"""confirm_reference — advance (or recover) the conformance baseline. (Command)

This is the "conformance baseline move" from solution spec §9.3 — the centerpiece's
write side. The agent, having applied a surfaced delta to the project's code, asserts
*"the code now conforms through this point."* zib **records** that assertion in
``confirmed_through``; it never inspects code to verify it (intent §3.5, spec §9.3:
"a trust action zib structurally cannot validate"). When the recorded baseline catches up
to the pin, the owed-delta gap closes — that gap is the whole correctness signal.

Two modes, exactly mirroring spec §9.3's ``confirm`` rows:

    confirm <name>             → confirmed_through = { current pin commit, its content_hash }
                                 (the agent applied the delta and is caught up to the pin)
    confirm <name> --to <x>    → move the baseline BACK to a retained ancestor of the pin
                                 (recover an over-assertion — spec §10 retention guarantees the
                                  one-step-back target tree is still on disk)

The ``--to`` mode requires a content_hash for the target (the baseline carries one to
integrity-check its retained tree — spec §9.3 / §10) and requires the target to be a genuine
*ancestor* of the current pin. Ancestry is a git fact the entity cannot decide from its own
data, so this capability validates it via the git port before mutating — exactly the
CLAUDE.md decision test ("needs external knowledge → caller validates, entity records").

Ordering (CLAUDE.md state-changer rule): mutate entity → persist lockfile. No agent-file
write here — confirm changes only the conformance baseline, which the inventory block does
not surface as content (it surfaces *owed delta*, recomputed on the next list/poll).

Pure stdlib + zib.core only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

from zib.core.entities.lockfile.lock_entry import Pin
from zib.core.entities.shared.value_objects import CommitSha, ContentHash, RefName
from zib.core.gateways.git.port.git_port import GitPort
from zib.core.ports.persistence.stores import LockfileStore, ManifestStore


@dataclass(frozen=True, slots=True)
class ConfirmResult:
    """The outcome of a confirm: which reference, and the commit now confirmed through."""

    name: str
    confirmed_commit: str


class ConfirmReference:
    """Advance or recover one reference's conformance baseline."""

    def __init__(
        self,
        manifest_store: ManifestStore,
        lockfile_store: LockfileStore,
        git_port: GitPort,
    ) -> None:
        self._manifest_store = manifest_store
        self._lockfile_store = lockfile_store
        self._git_port = git_port

    def execute(
        self,
        name: str,
        to_commit: CommitSha | None = None,
        to_content_hash: ContentHash | None = None,
    ) -> ConfirmResult:
        ref_name = RefName(name)

        lockfile = self._lockfile_store.read()
        entry = lockfile.get(ref_name)
        if entry is None:
            raise ValueError(f"no locked reference named {name!r} to confirm")

        if to_commit is None:
            # Caught up to the pin: assert conformance through the current pin exactly.
            baseline = entry.pin
        else:
            # Recovery (`confirm --to`): move the baseline BACK to a retained ancestor.
            if to_content_hash is None:
                raise ValueError(
                    "confirm --to requires the target's content hash "
                    "(the baseline integrity-checks its retained tree)"
                )
            manifest = self._manifest_store.read()
            reference = manifest.by_name(ref_name)
            if reference is None:
                raise ValueError(f"no declared reference named {name!r} to confirm")
            if not self._git_port.is_ancestor(
                reference.source, to_commit, entry.pin.commit
            ):
                raise ValueError(
                    f"{to_commit.short()} is not an ancestor of the current pin "
                    f"{entry.pin.commit.short()}; confirm --to may only move the "
                    "baseline back to a retained ancestor"
                )
            baseline = Pin(commit=to_commit, content_hash=to_content_hash)

        entry.confirm(baseline)
        self._lockfile_store.write(lockfile)

        return ConfirmResult(
            name=str(ref_name),
            confirmed_commit=str(baseline.commit),
        )
