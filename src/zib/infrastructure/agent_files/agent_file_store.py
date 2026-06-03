"""MarkdownAgentFileStore — the real :class:`AgentFileStore`.

Secondary adapter. zib owns exactly one block inside ``AGENTS.md`` — the region between two
HTML-comment markers — and nothing else. ``write_inventory_block`` replaces the *interior*
of that block, preserving everything outside it verbatim (the developer's own prose is never
parsed or touched). ``ensure_claude_import`` makes sure ``CLAUDE.md`` pulls in ``AGENTS.md``
via the ``@AGENTS.md`` import line, so an agent reading ``CLAUDE.md`` always sees zib's
managed inventory.

Markers (stable; never localized — they are zib's contract with itself)::

    <!-- zib:begin -->
    ...managed inventory body...
    <!-- zib:end -->

Both writes are compare-before-write: if the file already says exactly what we would write,
it is left untouched (clean diffs / idempotent install).
"""

from __future__ import annotations

from pathlib import Path

AGENTS_FILENAME = "AGENTS.md"
CLAUDE_FILENAME = "CLAUDE.md"

_BEGIN = "<!-- zib:begin -->"
_END = "<!-- zib:end -->"
_CLAUDE_IMPORT = "@AGENTS.md"
_CLAUDE_IMPORT_LINE = (
    "@AGENTS.md  <!-- zib: agent inventory (managed); imported so agents read it -->"
)


class MarkdownAgentFileStore:
    """Maintains the ``AGENTS.md`` managed block and the ``CLAUDE.md`` import."""

    def __init__(self, project_root: Path) -> None:
        """Bind the store to a project root (``AGENTS.md`` / ``CLAUDE.md`` live there)."""
        self._root = Path(project_root)

    def write_inventory_block(self, body: str) -> None:
        """Replace the interior of zib's managed block in ``AGENTS.md`` with ``body``.

        Everything outside the markers is preserved exactly. If the file has no managed block
        yet (or no file at all), the block is appended (a heading is added for a fresh file).
        """
        path = self._root / AGENTS_FILENAME
        block = f"{_BEGIN}\n{body}\n{_END}"

        if not path.is_file():
            content = f"# AGENTS.md\n\n{block}\n"
            self._write_if_changed(path, content)
            return

        existing = path.read_text(encoding="utf-8")
        start = existing.find(_BEGIN)
        end = existing.find(_END)
        if start != -1 and end != -1 and end > start:
            new = existing[:start] + block + existing[end + len(_END):]
        else:
            # No managed block yet — append one, separated by a blank line.
            sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
            new = existing + sep + block + "\n"
        self._write_if_changed(path, new)

    def ensure_claude_import(self) -> None:
        """Ensure ``CLAUDE.md`` imports ``AGENTS.md`` via an ``@AGENTS.md`` line.

        Idempotent: if an ``@AGENTS.md`` import is already present (in any form) nothing
        changes. A missing file is created with the import; an existing file gets the import
        prepended after its first heading (or at the top).
        """
        path = self._root / CLAUDE_FILENAME
        if not path.is_file():
            content = f"# CLAUDE.md\n\n{_CLAUDE_IMPORT_LINE}\n"
            self._write_if_changed(path, content)
            return

        existing = path.read_text(encoding="utf-8")
        if _CLAUDE_IMPORT in existing:
            return  # already imported (idempotent)

        lines = existing.splitlines(keepends=True)
        # Insert after a leading H1 heading if present, else at the very top.
        insert_at = 0
        if lines and lines[0].lstrip().startswith("# "):
            insert_at = 1
            # skip a blank line right after the heading, if any
            if len(lines) > 1 and lines[1].strip() == "":
                insert_at = 2
        injected = _CLAUDE_IMPORT_LINE + "\n\n"
        new = "".join(lines[:insert_at]) + injected + "".join(lines[insert_at:])
        self._write_if_changed(path, new)

    @staticmethod
    def _write_if_changed(path: Path, content: str) -> None:
        if path.is_file() and path.read_text(encoding="utf-8") == content:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
