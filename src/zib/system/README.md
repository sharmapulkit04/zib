# zib system references

These are zib's **own bundled references** — shipped inside the `zib` package and materialized into a
project by `zib init` (forthcoming). They are **version-matched to the installed zib** (they ship
together), so the integration guidance always matches the tool you have.

They are read by the **AI agent operating zib** — not by zib itself (zib stays deterministic and
dumb; see `decisions.md` DS7).

| Reference | Read it to… |
|---|---|
| [`integration/`](integration/OVERVIEW.md) | wire zib into your host (Claude Code, Cursor, a custom app, an enterprise platform) |
| [`usage/`](usage/OVERVIEW.md) | learn the day-to-day verbs and the update loop |
| [`authoring/`](authoring/OVERVIEW.md) | author a good reference (the producer discipline) |

Customize for your project in the consumer's `notes.md`, never here — these are zib's, not yours.

> Distinct from a **user reference** (a domain library/spec you pin): these are **system
> references**, zib's own infrastructure, bundled and version-locked to the tool. v1 keeps the set
> small on purpose (DS7 minimalism); more can be added without a "system package manager."
