"""Composition root — the ONE place that knows concrete adapters (CLAUDE.md).

It binds the persistence stores to a project root and the git adapter to the system git CLI,
wires the gateway processes onto the git port, and assembles each capability with its
dependencies. The CLI commands receive a fully-wired :class:`Container` and never construct
an adapter themselves — they are thin (parse → call capability → format).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zib.core.capabilities.add_reference.add_reference import AddReference
from zib.core.capabilities.confirm_reference.confirm_reference import ConfirmReference
from zib.core.capabilities.diff_reference.diff_reference import DiffReference
from zib.core.capabilities.init.init import InitCapability
from zib.core.capabilities.install.install import Install
from zib.core.capabilities.list_references.list_references import ListReferences
from zib.core.capabilities.outdated.outdated import Outdated
from zib.core.capabilities.read_reference.read_reference import ReadReference
from zib.core.capabilities.remove_reference.remove_reference import RemoveReference
from zib.core.capabilities.show_reference.show_reference import ShowReference
from zib.core.capabilities.update_reference.update_reference import UpdateReference
from zib.core.gateways.git.fetch.process.fetch_process import FetchProcess
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.resolve.process.resolve_process import ResolveProcess
from zib.infrastructure.agent_files.agent_file_store import MarkdownAgentFileStore
from zib.infrastructure.git.git_cli_adapter import GitCliAdapter
from zib.infrastructure.persistence.content_store import FileContentStore
from zib.infrastructure.persistence.lockfile_store import TomlLockfileStore
from zib.infrastructure.persistence.manifest_store import TomlManifestStore


@dataclass(frozen=True)
class Container:
    """The wired application — one assembled capability per CLI verb."""

    project_root: Path
    init: InitCapability
    add: AddReference
    install: Install
    list_references: ListReferences
    outdated: Outdated
    diff: DiffReference
    confirm: ConfirmReference
    update: UpdateReference
    remove: RemoveReference
    show: ShowReference
    read: ReadReference


def build_container(project_root: Path) -> Container:
    """Assemble every capability against the real adapters rooted at ``project_root``."""
    root = Path(project_root)

    # Secondary adapters (driven side).
    manifest_store = TomlManifestStore(root)
    lockfile_store = TomlLockfileStore(root)
    content_store = FileContentStore(root)
    agent_file_store = MarkdownAgentFileStore(root)
    git_port = GitCliAdapter()

    # Gateway processes onto the git port.
    resolve_process = ResolveProcess(git_port)
    fetch_process = FetchProcess(git_port)
    notes_process = NotesProcess(git_port)

    return Container(
        project_root=root,
        init=InitCapability(manifest_store, agent_file_store),
        add=AddReference(
            manifest_store,
            lockfile_store,
            content_store,
            agent_file_store,
            resolve_process,
            fetch_process,
        ),
        install=Install(
            manifest_store,
            lockfile_store,
            content_store,
            agent_file_store,
            resolve_process,
            fetch_process,
        ),
        list_references=ListReferences(manifest_store, lockfile_store),
        outdated=Outdated(manifest_store, lockfile_store, git_port),
        diff=DiffReference(manifest_store, lockfile_store, notes_process),
        confirm=ConfirmReference(manifest_store, lockfile_store, git_port),
        update=UpdateReference(
            manifest_store,
            lockfile_store,
            content_store,
            agent_file_store,
            resolve_process,
            fetch_process,
            notes_process,
        ),
        remove=RemoveReference(
            manifest_store, lockfile_store, content_store, agent_file_store
        ),
        show=ShowReference(manifest_store, lockfile_store),
        read=ReadReference(manifest_store, lockfile_store, content_store),
    )
