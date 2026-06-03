# Installing zib — an agent-readable spec

> **Hand this file to any AI coding agent.** It is a self-contained spec for installing zib into a
> project and wiring it up. No prior knowledge of zib is required.
>
> **What zib is:** a reference manager for AI coding agents. It pins versioned external references
> (specs, SDKs, conventions) and, on update, foregrounds *exactly what changed* so you apply it
> without missing anything. zib is deterministic and never executes anything — you (the agent)
> supply the judgment.
>
> **Status: early development.** `pip install zib` works today. Steps marked **(forthcoming)**
> depend on the CLI, which is landing next; until then, follow the conceptual flow and `README.md`.

---

## 1. Install the tool

```sh
pip install zib          # or: pipx install zib  |  uv tool install zib
```

Verify:

```sh
python -c "import zib; print('zib installed')"
# (forthcoming) zib --version
```

## 2. Initialize zib in the project — (forthcoming CLI)

```sh
zib init
```

`zib init` will:
- create the project manifest (`zib.toml`) and lockfile,
- materialize the **bundled system references** (§4) — zib's own integration/usage/authoring guidance,
- write a tiny discovery anchor into `AGENTS.md` (and `CLAUDE.md` = `@AGENTS.md` for Claude) so any
  agent knows zib is present and what to run.

## 3. Read the `integration` system reference

After `zib init`, read **`integration`** (§4). It adapts zib to *your* environment — Claude Code,
Cursor, a custom app, an enterprise platform — and tells you how to deliver zib's verbs and live
state to yourself. If no recipe fits your host, the **self-describing CLI alone is enough** (§5).

## 4. The bundled system references ("system packages")

zib ships with its own references, materialized by `zib init` and **version-matched to the installed
zib** (they ship together):

| System reference | Read it to… |
|---|---|
| `integration` | wire zib into your host (Claude Code, Cursor, custom app, enterprise) |
| `usage` | learn the day-to-day verbs and the update loop |
| `authoring` | author a good reference (the producer discipline) |

These are read by *you*, the agent — not by zib (zib stays deterministic and dumb).

## 5. How you operate zib (the floor — works in any agent)

zib's commands **emit context**: you run zib and read its output. The core loop:

```
add a reference    → zib add <name> --source <git-url> --spec <version>
see what's pending → zib status   (or zib outdated)
apply an update    → zib diff <name>  →  apply to code  →  zib confirm <name>
```

*(All commands forthcoming with the CLI.)* The CLI is self-describing — run `zib` or `zib --help`
and follow the next step it prints. You won't need this file again after install.

## 6. Customize — in *your* notes, not zib's

Project-specific usage ("how *this* project uses a reference") goes in the consumer's `notes.md`.
zib stores it verbatim, never parses it, and it survives updates. The system references in §4 are
zib's; your `notes.md` is yours.

---

**The whole bootstrap:** `pip install zib` → `zib init` → read the **`integration`** system
reference → operate via the self-describing CLI. The deterministic CLI is the floor; this spec just
gets you there.
