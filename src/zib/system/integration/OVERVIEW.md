# Integrating zib into your environment

> A bundled **system reference**. Read this to wire zib into *your* host so that you (the agent) have
> zib's verbs and live state. zib provides the menu + the deterministic CLI; **you detect your
> environment and apply the right recipe.** If no recipe fits, the self-describing CLI alone is enough.

## The model (works for any agent)

- **Discovery floor:** a tiny block in `AGENTS.md` (and `CLAUDE.md` = `@AGENTS.md` for Claude — Claude
  reads only `CLAUDE.md`) that says *"this project uses zib; run `zib status`."* `zib init` writes it.
  Keep it small — it's always-on context.
- **The substance is the CLI:** zib's commands **emit context** — `zib status` / `zib diff` print what
  you need, fresh, on demand. You operate zib by running it and reading its output. This works in any
  agent that can run a shell, with zero priming.
- **Optional accelerants (per host):** the recipes below make it smoother where supported. None is
  required for correctness.

## Recipes by host

### Claude Code
- `AGENTS.md` discovery block + `CLAUDE.md` importing it (`@AGENTS.md`).
- Optional: a **Skill** (`.claude/skills/zib/SKILL.md`) that wraps the CLI — its description is
  always-on (cheap), its body loads on demand, and it can inject `zib status` output.
- Optional: a `SessionStart` hook that injects `zib outdated` so you start already knowing what's pending.

### Cursor / Copilot / others
- A **rule** (`.cursor/rules/…`) or **instructions** file pointing at `zib status` and the update loop.

### Custom app / enterprise platform
- Call zib via the **CLI** (subprocess) or import its **capabilities** directly; consume the
  **structured (`--json`, forthcoming)** output in your own context-builder and inject it into your
  prompt. Verify with the integration evals.

## Verify the integration

Run the integration evals (forthcoming): they confirm you can *discover* zib, *read* its state, and
*drive* the update loop. A green eval is your evidence the wiring works.

## Principles — do not break these

- **zib never detects your agent.** *You* pick the recipe; zib only provides the menu + templates.
- **The CLI floor must work with zero priming** — every recipe sits on top of it, never replaces it.
- **Correctness rests on zib's verify/confirm gate**, not on this integration succeeding. A perfectly
  wired host and a blank one both hit the same deterministic gate.
