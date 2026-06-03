"""zib CLI — the primary adapter (app shell).

Thin commands: each parses arguments, calls exactly one capability through the composition
root, and formats the result for an agent (or human) to read. No business logic lives here —
conditionals are presentation-only (CLAUDE.md invariant 5). Output is agent-readable: the
resolved label/commit/hash on ``add``, a clear table on ``list``/``status``, the delta on
``diff``.
"""

from __future__ import annotations

from pathlib import Path

import click

import re

from zib.app_cli.config.composition_root import build_container
from zib.core.entities.shared.semver import Range
from zib.core.entities.shared.value_objects import RefSpec

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _spec_from_inputs(
    version: str | None,
    branch: str | None,
    tag: str | None,
    rev: str | None,
) -> RefSpec:
    """Build a :class:`RefSpec` from the add flags (shell-side input parsing).

    Explicit ``--branch`` / ``--tag`` / ``--rev`` always win and map to their lane. The
    catch-all ``--spec`` is classified by shape — this is presentation-layer parsing of one
    CLI string into the manifest's existing mutually-exclusive lanes, not a domain decision:

        "latest"                  -> LATEST
        a parseable semver range  -> SEMVER   (^2.1.0, ~1.2, 2.1.4, 1.x, *)
        a 40-hex sha              -> REV
        anything else             -> BRANCH   (a branch/tag name like ``main``)
    """
    explicit = {"branch": branch, "tag": tag, "rev": rev}
    given = {k: v for k, v in explicit.items() if v is not None}
    if version is not None and given:
        raise click.UsageError("use either --spec or one of --branch/--tag/--rev, not both")
    if given:
        return RefSpec.from_manifest(**given)
    if version is None:
        raise click.UsageError("a reference needs --spec (or --branch/--tag/--rev)")

    if version == "latest":
        return RefSpec.from_manifest(version="latest")
    if _SHA_RE.match(version):
        return RefSpec.from_manifest(rev=version)
    try:
        Range.from_spec(version)
    except ValueError:
        # Not a semver constraint → treat as a moving branch ref (the common case for a
        # branch-tracked source with no tags).
        return RefSpec.from_manifest(branch=version)
    return RefSpec.from_manifest(version=version)


def _container(ctx: click.Context):
    return build_container(ctx.obj["root"])


@click.group()
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project root (defaults to the current directory).",
)
@click.pass_context
def cli(ctx: click.Context, root: Path | None) -> None:
    """zib — a reference manager for AI coding agents."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = (root or Path.cwd()).resolve()


# --------------------------------------------------------------------------- init


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Scaffold a fresh zib workspace (zib.toml + agent files)."""
    result = _container(ctx).init.execute()
    if result.created:
        click.echo("Initialized zib workspace (zib.toml, AGENTS.md, CLAUDE.md import).")
    else:
        click.echo("zib workspace already initialized — nothing to do.")


# --------------------------------------------------------------------------- add


@cli.command()
@click.argument("name")
@click.option("--role", required=True, help="The slot this reference fills (e.g. architecture).")
@click.option("--source", required=True, help="Git source: local path, URL, or owner/repo.")
@click.option("--spec", "version", default=None, help="Version constraint (^2.1.0 / 2.1.4 / latest).")
@click.option("--branch", default=None, help="Track a branch tip.")
@click.option("--tag", default=None, help="Pin a literal release tag.")
@click.option("--rev", default=None, help="Freeze at a 40-hex commit SHA.")
@click.option("--subdirectory", default=None, help="Scope the reference to a subdirectory.")
@click.option("--description", default=None, help="Selection aid the agent reads.")
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    role: str,
    source: str,
    version: str | None,
    branch: str | None,
    tag: str | None,
    rev: str | None,
    subdirectory: str | None,
    description: str | None,
) -> None:
    """Add and pin a new reference NAME (resolves, fetches, hashes, materializes)."""
    try:
        spec = _spec_from_inputs(version, branch, tag, rev)
    except ValueError as exc:
        raise click.UsageError(str(exc)) from exc

    try:
        result = _container(ctx).add.execute(
            name=name,
            role=role,
            source=source,
            spec=spec,
            subdirectory=subdirectory,
            description=description,
        )
    except (ValueError, KeyError) as exc:
        raise click.ClickException(str(exc).strip("'")) from exc

    click.echo(f"Added '{result.name}'")
    click.echo(f"  resolved: {result.resolved_label}")
    click.echo(f"  commit:   {result.commit}")
    click.echo(f"  content:  {result.content_hash}")


# --------------------------------------------------------------------------- install


@cli.command()
@click.pass_context
def install(ctx: click.Context) -> None:
    """Materialize all references at their locked pins (idempotent)."""
    result = _container(ctx).install.execute()
    if not result.installed and not result.verified:
        click.echo("All references already installed and verified — nothing changed.")
        return
    for nm in result.installed:
        click.echo(f"installed  {nm}")
    for nm in result.verified:
        click.echo(f"re-fetched {nm}")


# --------------------------------------------------------------------------- list


@cli.command(name="list")
@click.pass_context
def list_cmd(ctx: click.Context) -> None:
    """List every declared reference and its pinned state."""
    rows = _container(ctx).list_references.execute()
    if not rows:
        click.echo("No references declared. Run `zib add <name> ...` to add one.")
        return
    _print_table(
        ["NAME", "ROLE", "TYPE", "RESOLVED", "PENDING"],
        [
            [r.name, r.role, r.ref_type, r.resolved, "yes" if r.owed_delta else "-"]
            for r in rows
        ],
    )


# --------------------------------------------------------------------------- status / outdated


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Poll every reference (read-only): upstream drift + owed delta."""
    _print_outdated(_container(ctx).outdated.execute())


@cli.command()
@click.pass_context
def outdated(ctx: click.Context) -> None:
    """Alias of `status`: read-only freshness poll."""
    _print_outdated(_container(ctx).outdated.execute())


def _print_outdated(items) -> None:
    if not items:
        click.echo("No installed references to poll.")
        return
    _print_table(
        ["NAME", "DRIFT", "TARGET", "PENDING"],
        [
            [it.name, it.drift_status, it.target or "-", "yes" if it.owed_delta else "-"]
            for it in items
        ],
    )


# --------------------------------------------------------------------------- diff


@cli.command()
@click.argument("name")
@click.pass_context
def diff(ctx: click.Context, name: str) -> None:
    """Show the unconfirmed delta for reference NAME (read-only)."""
    try:
        result = _container(ctx).diff.execute(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.has_pending:
        click.echo(f"'{name}' is up to date — nothing to confirm.")
        return
    if result.read_whole:
        reason = "first encounter" if result.delta is None else "substantial rewrite"
        click.echo(f"'{name}' — {reason}: read the whole reference (`zib show {name}` / .zib/references/{name}/).")
    if result.delta is not None:
        delta = result.delta
        click.echo(f"# delta for '{name}' (magnitude: {delta.magnitude.value})")
        if delta.tag_notes:
            click.echo("## release notes")
            click.echo(delta.tag_notes)
        if delta.commits:
            click.echo("## commits")
            for c in delta.commits:
                click.echo(f"  {c.commit.short()} {c.subject}")
        if delta.diff_text:
            click.echo("## diff")
            click.echo(delta.diff_text)
    click.echo(f"\nApply it, then run `zib confirm {name}`.")


# --------------------------------------------------------------------------- confirm


@cli.command()
@click.argument("name")
@click.pass_context
def confirm(ctx: click.Context, name: str) -> None:
    """Assert the code conforms through NAME's current pin."""
    try:
        result = _container(ctx).confirm.execute(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Confirmed '{result.name}' through {result.confirmed_commit[:7]}.")


# --------------------------------------------------------------------------- update


@cli.command()
@click.argument("name")
@click.pass_context
def update(ctx: click.Context, name: str) -> None:
    """Re-resolve NAME within its constraint, re-pin, and surface the delta."""
    try:
        result = _container(ctx).update.execute(name)
    except (ValueError, KeyError) as exc:
        raise click.ClickException(str(exc).strip("'")) from exc
    if result.up_to_date:
        click.echo(f"'{name}' is already up to date at {result.old_commit}.")
        return
    click.echo(f"Updated '{name}': {result.old_commit} -> {result.new_commit}")
    if result.magnitude is not None:
        click.echo(f"  change magnitude: {result.magnitude.value}")
    click.echo(f"  run `zib diff {name}` to see what changed, apply it, then `zib confirm {name}`.")


# --------------------------------------------------------------------------- remove


@cli.command()
@click.argument("name")
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    """Remove NAME from the manifest, lockfile, and materialized content."""
    try:
        result = _container(ctx).remove.execute(name)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Removed '{result.name}'.")


# --------------------------------------------------------------------------- helpers


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    for row in rows:
        click.echo(fmt.format(*[str(c) for c in row]))


if __name__ == "__main__":  # pragma: no cover
    cli()
