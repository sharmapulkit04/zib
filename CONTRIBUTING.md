# Contributing to zib

Thanks for your interest! zib is early-stage, so the most valuable contributions right now are
**issues** — bug reports, design feedback, and real use cases.

## Development setup

```sh
pip install -e ".[dev]"   # or: uv pip install -e ".[dev]"
pytest                    # fast — runs in seconds
```

## Architecture, in one breath

zib is **hexagonal (ports & adapters) + DDD**. The one rule: **`core/` depends on nothing** — no
framework, no I/O. Infrastructure and the app shells depend on `core/`, never the reverse.

- `core/` — pure behavior: entities, rules, capabilities, ports, gateways
- `tests/` — mirrors `core/`; rules are exhaustively unit-tested, capabilities are scenario-tested
- `decisions.md` — the design decision log; read it to understand *why* things are the way they are

## Proposing changes

1. **Open an issue first** for anything non-trivial, so we can agree on direction.
2. Fork, branch, and keep `pytest` green (add tests for new behavior).
3. Match the surrounding style; one concern per file.
4. Open a PR referencing the issue.

## Conventions that matter

- **`core/` imports no third-party libraries** — semver, hashing, etc. are pure stdlib in core.
- **Tests assert concrete values**, not shapes.
- **New design decisions** earn a short entry in `decisions.md`.

By contributing, you agree your contributions are licensed under the project's MIT license.
