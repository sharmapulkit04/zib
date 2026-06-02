"""render_inventory rule — the markdown the agent reads to know what exists.

This is the *body* of zib's managed block in ``AGENTS.md`` (solution spec §11.2/§11.3,
intent §3.2/§3.6). The runtime consumer is an AI coding agent: it scans this body to pick
the right reference for the user's instruction (by ``role`` + ``description``), learns where
each reference's content lives (``.zib/references/<name>/``), at what version it is pinned
(``resolved``), and — critically (intent §3.2) — whether a change is *pending to apply*
(``owed_delta`` → a loud ``UPDATE PENDING`` line that names the exact command to run).

Pure string building. No I/O, no parsing, no judgment — the tool is deterministic and dumb;
the agent supplies the intelligence. Ordering is by ``name`` so the rendered block is stable
across runs (a clean diff when the reference set is unchanged).

Pure stdlib only — this is core/.
"""

from __future__ import annotations

from dataclasses import dataclass

# The on-disk root for materialized reference content (solution spec §6/§11.2).
# Each reference's bytes live under ``.zib/references/<name>/``.
_CONTENT_ROOT = ".zib/references"

# What the agent reads when nothing is pinned yet. Stable so the block round-trips cleanly.
_EMPTY_BODY = (
    "## Managed references (zib)\n"
    "\n"
    "No references are pinned yet. Run `zib add <name> --role <role> --git <repo>` to add one."
)


@dataclass(frozen=True, slots=True)
class InventoryItem:
    """One reference's selection-facing summary — no content, just orientation.

    ``description`` is the selection aid (manifest → ``zib.ref.toml`` → ``name · role``
    cascade resolved upstream; may be ``None``). ``owed_delta`` is True when the pin is
    ahead of the agent's confirmed conformance baseline — a change the agent still owes.
    """

    name: str
    role: str
    ref_type: str
    resolved: str
    description: str | None
    owed_delta: bool


def render_inventory(items: list[InventoryItem]) -> str:
    """Render the markdown body of zib's managed ``AGENTS.md`` inventory block.

    Items are sorted by ``name`` for deterministic output. An empty list yields a stable
    "no references" body. Each item renders one ``name · role · description`` selection line,
    its pinned version + on-disk content path, and — when ``owed_delta`` — a loud
    ``UPDATE PENDING`` line naming ``zib diff <name>``.
    """
    if not items:
        return _EMPTY_BODY

    ordered = sorted(items, key=lambda item: item.name)

    lines: list[str] = [
        "## Managed references (zib)",
        "",
        "Pick by matching the user's need to a role/description, then `zib cat <name>`:",
        "",
    ]

    for item in ordered:
        description = item.description if item.description else f"{item.name} · {item.role}"
        lines.append(f"### {item.name} · {item.role}")
        lines.append(f"- {description}")
        lines.append(f"- pinned: {item.resolved} ({item.ref_type})")
        lines.append(f"- content: {_CONTENT_ROOT}/{item.name}/")
        if item.owed_delta:
            lines.append(f"- UPDATE PENDING: run `zib diff {item.name}` to see what changed, "
                         f"apply it, then `zib confirm {item.name}`")
        lines.append("")

    # Drop the trailing blank line so the body ends cleanly.
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)
