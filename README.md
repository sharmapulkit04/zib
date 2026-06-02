# zib

> **Hew to your references.** Know exactly what changed; conform with confidence.

A **reference manager for AI coding agents**. zib pins versioned external references —
specs, frameworks, and conventions you read *as reference* — from git repositories into
your project, so your AI coding agent reads the right reference, at the right version,
with **exactly what changed** foregrounded on every update.

You don't run zib by hand. You talk to your agent ("install our specs", "update the auth
spec", "find a better fit for this need"); the agent uses zib to fetch, pin, and surface,
then applies the reference to your code and records project-specific usage notes.

> Status: **early development.** The pure core (entities, rules, port contracts) is landing
> first; capabilities, the git adapter, and the CLI follow. See `decisions.md` for the
> architecture and language rationale, and `reference-manager-intent.md` for the north star.

## Why git-pinned

Each reference is pinned to an immutable commit **and** a content hash of the exported tree,
so anyone who checks out your project gets the identical reference and can reproduce it
exactly (precedent: Nix `flake.lock`, Go `go.sum`, Cargo). On update, zib shows the agent
the precise difference from the last point you confirmed — never the whole reference again.

## Development

```sh
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"
pytest
```

Architecture: hexagonal (ports & adapters) + DDD — `core/` is pure and depends on nothing.
See `decisions.md`.

## License

MIT
