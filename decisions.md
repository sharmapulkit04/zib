# decisions.md

> The decision log for zib. Two series: **D** = foundational technology choices,
> **DS** = design decisions (the dimension-by-dimension resolutions). Append-only,
> small, lives in the code repo. Format: **MADR-lite** (Context · Options · Decision ·
> Consequences), plus a **Serves** field naming the intent principle each design
> decision honors — per `reference-manager-intent.md` (the north star, which wins on
> conflict).
>
> **How to use it.** Decompose the problem into dimensions → decide each *against an
> intent principle* (a decision that can't cite one is scope creep — cut it) → record a
> row here. Scan the **Index** to see where everything stands; read the body only for
> the *why*. This is the antidote to tracking decisions in chat scrollback.

---

## Index — the at-a-glance ledger

| ID | Decision | Status | Serves |
|---|---|---|---|
| D1 | Architecture: hexagonal / DDD, right-sized to a CLI | Accepted | — |
| D2 | Language: Python 3.10+ (migrate later only if blocked) | Accepted | — |
| D3 | Layout: src-layout, pipx/uv-installable | Accepted | — |
| D4 | Deps: click, tomlkit; semver pure-stdlib in core | Accepted | — |
| D5 | Pin: git commit SHA + exported-tree content_hash | Accepted | — |
| D6 | content_hash: canonical, attribute-blind tree hash | Accepted | — |
| D7 | Design input: intent + solution specs | Accepted | — |
| DS1 | Source for integration: don't vendor — pin the real repo | Accepted | describe-not-restate · foreground-change |
| DS2 | Source binding: no separate file when co-located | Accepted | minimalism |
| DS3 | Adoption: references without a package (on-the-go generation) | **Proposed** | agent-judgment · minimalism |
| DS4 | Diff ownership: zib computes, agent interprets | Accepted (in code) | dumb-tool · foreground-change |
| DS5 | Per-release "what changed" signal (+ degradation by RefKind) | Accepted | foreground-change |
| DS6 | Installation-concern package design (`examples/INSTALLING.md`) | **Proposed** | foreground-change · agent-is-consumer · dumb-tool |
| DS7 | Agent-context delivery model (how the agent gets verbs + live state) | **🔄 Active** | agent-is-consumer · dumb-tool · minimalism |
| DS8 | Tool name: keep `zib` (not `hew`); "hew to" → tagline | Accepted | — |

**Status legend:** Accepted · Proposed (drafted, awaiting ratification) · 🔄 Active (live discussion, being improved) · Open (undecided) · Superseded.

## Intent principles — the test every DS must cite

From `reference-manager-intent.md` §2:

1. **describe-not-restate** — the reference describes itself; author only the delta.
2. **foreground-the-change** — on update, surface what changed, never the whole.
3. **agent-is-consumer** — the runtime reader is an AI agent.
4. **dumb-tool / agent-judgment** — zib fetches/pins/diffs deterministically; judgment is the agent's.
5. **minimalism** — include nothing the problem doesn't require.

---

## Foundational decisions (D-series — all Accepted)

## D1 — Architecture: hexagonal / DDD, right-sized to a CLI

zib follows the hexagonal (ports & adapters) + DDD architecture in
`/Users/pulkit/projects/CLAUDE.md`. It fits unusually well because the spec was
already built around the same instincts (a "dumb, deterministic tool; the agent
has the judgment" = a pure core; the "source-adapter seam" = a gateway + port).

Right-sizing decisions (faithful, not bloated):

- **One shell** — `app_cli`. No `app-web` / `app-worker`. "Shells are disposable,"
  so a future MCP/daemon shell drops in without touching core (MCP stays deferred).
- **The git interaction is a gateway** (`core/gateways/git/`), not a plain port —
  it needs transformation, rules (semver pick, ref deref), and a translator.
  Its driven boundary is `GitPort`, which infrastructure implements via the git CLI.
- **Sync git gateway → no gateway entity.** All git calls block; there is no async
  correlation lifecycle, so the gateway collapses to process + rules + translator + port
  (entities are async-only per CLAUDE.md).
- **No domain events** — zib v1 has no event consumers (CLAUDE.md says skip that part).

## D2 — Language: Python 3.10+ (working v1; migrate later only if a real blocker appears)

Chosen for the fastest path to a *working, validated* v1: the build is git-shelling +
TOML + semver + filesystem, all trivial in Python, and it matches prior familiarity.

**Migrate-later is explicitly safe here, by construction** — this is why the
architecture was worth applying:

- `core/` is pure and framework-free; its logic (value objects, the conformance FSM,
  `content_hash`, version resolution) ports to Go/Rust ~1:1.
- The **scenarios are data** and run at two levels. A reimplementation re-runs the *same*
  scenario suite — the rewrite becomes "make these green," not "redesign."
- "Shells are disposable"; ports are language-agnostic contracts.

**Revisit trigger:** if startup latency (`list`/`info` <100ms budget) or single-static-binary
distribution becomes a real adoption blocker, port to Go or Rust keeping core logic 1:1.
Not before — premature for an unproven v1. (A CLI that shells out to `git` is usually
dominated by `git` itself, not interpreter start, so the budget is likely fine for v1.)

## D3 — Layout: src-layout (`src/zib/`), pipx/uv-installable

Modern Python packaging. `pythonpath = ["src"]` lets tests import `zib.*` without an install.

## D4 — Dependencies: click, tomlkit (core imports none; semver is pure-stdlib in core)

- `click` — the CLI shell (thin commands, shell completions, man pages).
- `tomlkit` — manifest read/write **preserving user formatting/comments**; canonical
  lockfile emission (we control the serialization for determinism).
- **Semver lives in core, implemented in pure stdlib.** Version resolution is core
  business logic, and core depends on nothing — so a third-party semver package
  (`semantic-version`, etc.) is disallowed there. `core/entities/shared/semver.py`
  implements the supported range subset (exact, `^`, `~`, x-ranges, `*`) + comparison,
  exhaustively unit-tested. This is the single semver implementation the rules reuse.

## D5 — Pin: git commit SHA + exported-tree content_hash (two-part)

The commit is the immutable pin; the content_hash anchors the exact bytes the agent reads.
Precedent: Nix `flake.lock` (rev + narHash), Go `go.sum`, Cargo (rev), git submodules.

## D6 — content_hash: canonical, attribute-blind tree hash

sha256 over the exported tree: NFC-normalized paths sorted by raw UTF-8 bytes, file modes
included, length-framed entries, symlinks hashed by target (not dereferenced). Blind to git
metadata (author/date) so it reflects *what the agent reads*, not how it was committed.

## D7 — Design input: the intent + solution specs

`reference-manager-intent.md` (the north star — wins on conflict) and
`reference-manager-solution.md` (the build spec) are the design files the CLAUDE.md design
workflow feeds in. They live alongside the code for now.

---

## Design decisions (DS-series — MADR-lite)

## DS1 — Source for integration: don't vendor; pin the real repo

**Status:** Accepted · **Serves:** describe-not-restate, foreground-the-change

**Context.** An agent integrating against a reference sometimes needs the library's
*actual source*, not just the curated prose. Should a zib package ship/vendor that source?

**Options.** (a) Vendor the source into the pinned tree. (b) Point to it (commit-pinned)
and let the agent fetch source via the real install or by browsing the repo.

**Decision.** Never vendor source (it's the thing run in production, a dependency, not a
reference). Pin the real repo at a commit; the agent obtains source from the real install
(e.g. site-packages) or by browsing the pinned commit with its own tools.

**Consequences.** Packages stay llms.txt-scale and diffs stay legible. Source is
*reproducible-by-commit*, not hash-pinned by zib — it survives only while upstream exists.
Binaries are never shipped (they defeat zib's text diff).

## DS2 — Source binding: no separate file when the package is co-located

**Status:** Accepted · **Serves:** minimalism

**Context.** How does a package define *where* the library's source lives? A curated
`SOURCE.md` (a version=commit binding plus a hand-picked file-pointer map) was proposed.

**Options.** (a) Curated `SOURCE.md` (binding + pointer tour). (b) A minimal structured
binding (`repo` + `version` + `commit`). (c) Nothing — reuse zib's own pin.

**Decision.** Drop the curated pointer map — a capable agent navigates a repo itself; the
only fact it can't derive is *which commit == the documented version*. When the package's
`source` **is** the library's own repo (co-located subtree via `subdirectory`, tagged in
lockstep), zib **already pins** `source` + `resolved` (version) + `pin.commit` — so define
nothing extra. A standalone binding is needed *only* when docs live in a different repo
than the code.

**Consequences.** `SOURCE.md` collapses to at most a one-line "the binding is zib's lock."
Prefer co-locating the package in the library repo. Caveat: lockstep tagging required, else
`resolved` ≠ the library version. **Refines** the `SOURCE.md` section of DS6.

## DS3 — Adoption: references without a package (on-the-go generation)

**Status:** Proposed · **Serves:** agent-judgment, minimalism

**Context.** ~99% of real repos ship no zib package / `INSTALL.md`. If zib only works on
producer-curated packages, it's useless on day one against the existing ecosystem.

**Options.** (a) Require producer-curated packages. (b) Generate the whole package on the
fly. (c) Tiered: pin real source + derive orientation on demand.

**Decision (proposed).** Two tiers. **Tier 1 (pinned)** = the real repo subtree @ commit —
always deterministic. **Tier 2 (orientation)** = curated if present, else agent-generated
from the repo's structured metadata. Install/API generate *reliably* (from
`pyproject`/signatures); PITFALLS/editorial do not. Generated orientation lives as the
**consumer's notes**, never pinned as reference (LLM prose isn't byte-deterministic — pinning
it would flood the update diff with rewording noise). May seed/upstream a real package later.

**Consequences.** zib works against any repo immediately; the producer-curated package
becomes the *ideal you graduate toward*, not a precondition. The mechanical net diff still
works because it diffs *real source*, not generated prose.

## DS4 — Diff ownership: zib computes the diff, the agent interprets it

**Status:** Accepted (implemented) · **Serves:** dumb-tool/agent-judgment, foreground-the-change

**Context.** Should zib implement the diff mechanism, or hand both versions to the agent
and let it describe what changed?

**Options.** (a) zib computes a mechanical diff. (b) The agent eyeballs both versions and
authors the change description.

**Decision.** zib owns the **mechanical, complete, deterministic** diff + magnitude routing
(`delta.py` churn → INCREMENTAL/REWRITE). The agent owns **interpretation** — meaning,
relevance, how to apply — layered *on top of* zib's diff, never replacing it. zib stops at
the textual/structural diff; semantic understanding is the agent's.

**Consequences.** A mechanical diff *structurally cannot* miss a changed byte — the exact
failure zib exists to prevent; an LLM comparison can. Concern-split files + stable filenames
give zib semantic-ish routing for free (which file changed = what kind of change). Already in
code: `rules/computation/delta`, `capabilities/diff_reference`, `gateways/git/notes`.

## DS5 — Per-release "what changed" signal

**Status:** Accepted · **Serves:** foreground-the-change (+ dumb-tool, agent-is-consumer)

**Context.** The mechanical diff shows *that* files changed, but not the per-release *intent*
("what happened in this release"), and it cannot infer **behavioral** breaks (the signature looks
identical). How do we reliably communicate per-release change, robust to multi-version jumps?
(Grounded in deep research across npm/PyPI/Cargo/Go/Java changelog + semver + API-diff practice.
Research conclusion: no single signal suffices — prose drifts, version numbers lie, mechanical
diffs are behavior-blind — so the answer is to *layer* three.)

**Options.** Human prose only / version-number only / mechanical diff only / a layered combo.

**Decision.** Three layers + one cross-check. Each sub-choice decided by the principle that governs it:

| Sub-choice | Governing principle | Verdict |
|---|---|---|
| Primary signal | foreground-change + dumb-tool | the **mechanical net diff** (endpoint-to-endpoint; complete; already in code) |
| `RELEASES.md` append-only, newest-first | foreground-change | yes — the **union** of intervening entries falls out of an append-only file's diff |
| `BREAKING:` / `BEHAVIORAL:` marker | agent-is-consumer | adopt as a producer **convention** (foregrounds impact; `BEHAVIORAL:` covers the diff's blind spot) |
| Enforce the marker? | dumb-tool | no — producer discipline; zib can't police prose |
| Parse the marker, or just surface it? | dumb-tool (only two fields parsed) | **surface only** — the agent reads the marker; zib never parses reference prose |
| semver-vs-churn cross-check | foreground-change + dumb-tool | yes — arithmetic on data zib already owns (version label + churn), not content interpretation |
| push delivery / yank channel | minimalism (v1 scope) | **deferred** (Open) |

**Degradation by RefKind.** The three layers assume a **tag/release**-tracked reference. They
degrade predictably as the ref kind loosens — and this is *already modeled* by the `Delta` type
(`core/gateways/git/notes/translator/notes_types.py`):

| Layer | SEMVER / TAG / LATEST | BRANCH | REV (frozen) |
|---|---|---|---|
| mechanical net diff (`Delta.diff_text`) | ✅ | ✅ **carries the whole load** | n/a (never moves) |
| churn magnitude (`Delta.magnitude`) | ✅ | ✅ (needs only diff stats) | n/a |
| `RELEASES.md` version-notes union | ✅ | ❌ no releases between tips | n/a |
| intent fallback | `RELEASES.md` | the **commit log** `(from, to]` (`Delta.commits` — the documented stand-in) | n/a |
| version/semver signal + cross-check | ✅ | ❌ no version | n/a |
| producer notes (`Delta.tag_notes`) | ✅ (tag-only) | ❌ `None` | n/a |

For a BRANCH the diff (+ churn routing) does almost all the work and the commit log stands in for
intent; the version-notes union, semver signal, and markers are absent. `LockEntry.is_frozen()`
short-circuits REV (update/poll is a no-op).

**Feature-branch reproducibility caveat.** A branch can be **force-pushed / rebased**, which can
orphan the exact commit zib pinned. Already-materialized content is safe (it lives in the project's
own VCS — see H4), but a *re-fetch* of that commit (`install._rematerialize`) fails if the commit
is gone from the remote. Tags/releases don't carry this risk. → feature branches are for genuinely
in-development references only; prefer tags for anything that must stay reproducible.

**Consequences.** Behavioral changes surface *only if the producer wrote them down* → `RELEASES.md`
must mandate `BEHAVIORAL:` call-outs. Don't trust prose alone (drifts) or the version alone (semver
violations) — the mechanical diff is the floor. **No code change required for the degradation** — the
`Delta` type already carries `diff_text` + `commits` (branch stand-in) + `magnitude` + tag-only
`tag_notes`. **Built:** the `BREAKING:`/`BEHAVIORAL:` marker convention (in `examples/INSTALLING.md`
+ the acme-orders `RELEASES.md` exemplar); the semver-vs-churn cross-check as a core rule
(`core/rules/validation/version_churn_agreement` — `classify_bump` + `verdict_for` +
`assess_version_churn`, exhaustively tested). **Not yet wired:** the cross-check rule is not yet
called by a capability — `update_reference` is the natural site (it holds both the old and new
version labels at repin time; `confirmed_through` does not store a label). **Refines** the
`RELEASES.md` section of DS6. Open: active-vs-passive surfacing, yank/advisory channel.

## DS6 — Installation-concern package design (`examples/INSTALLING.md`)

**Status:** Proposed (drafted) · **Serves:** foreground-the-change, agent-is-consumer, dumb-tool

**Context.** How should a zib package be shaped for the *installation* concern, so an agent
installs the right **real** dependency, at a version **aligned** with the pinned reference,
reproducibly, and so install changes diff cleanly? (Produced by a multi-lens design panel.)

**Decision (proposed).** Captured in full in `examples/INSTALLING.md`. Key sub-decisions:
- **Anchor vs window** — document one exact anchor version; install a window with `floor == anchor`, `ceiling == next prose-breaking major`.
- **Verify = exit-code assertion**, not a `# expect` comment.
- **Generated-from-source** — all version-coupled prose emitted from one `ANCHOR_VERSION + ANCHOR_COMMIT` at release time.
- **No machine-readable lock shipped** — the verify command's exit code is the contract; a shipped `install.lock` would duplicate the real package-manager lockfile and break zib's two-field rule.
- **Two gates** — offline `INSTALL.md` verify (presence + version), then sandboxed `evals/` (behavior).
- **Alignment flexes by RefKind** — window+band for SEMVER/TAG, exact for REV, VCS-install for BRANCH.
- **Transitive deps listed only when actionable.**

**Consequences.** DS2 and DS5 **refine** this doc's `SOURCE.md` and `RELEASES.md` sections →
`examples/INSTALLING.md` needs an update to match (open follow-up). See that file for detail.

## DS7 — Agent-context delivery model 🔄 ACTIVE / EVOLVING

**Status:** Active (deliberately *not* frozen — this is a live discussion; the "Open threads"
below are meant to be worked, and the decision revised as the mechanism improves) ·
**Serves:** agent-is-consumer, dumb-tool, minimalism

> **This entry is a working document.** It records current best thinking from a multi-turn
> discussion + two deep-research passes — not a closed verdict. Revise it in place as we improve
> the mechanism; keep the "Open threads" section honest.

**Context.** The agent operates zib, so it must acquire both (a) the *procedural* know-how (the
verbs + the poll→update→diff→apply→confirm / add→install→verify→confirm loops) and (b) the *live
state* (what's outdated, what delta is owed) — across **infinite agent-framework variation**,
without bloating the context window, and given that zib **cannot control the agent's runtime**.

**Decision (current).** A layered, graceful-degradation model, with determinism pushed to the
parts zib actually controls. Top layer runs once at install; the rest at runtime.

| Layer | Delivers | When | Notes |
|---|---|---|---|
| **0. Install-time self-wiring** | sets up the right adapter | once (`zib init`) | agent runs it; zib emits a **decision table + adapter templates**; the agent **self-identifies its env** and writes the best adapter. Idempotent, re-runnable. |
| **1. Always-on pointer** | discovery + owed-delta flags | every turn | the managed inventory block. Content home = **`AGENTS.md`** (cross-tool); Claude reads it via a generated **`CLAUDE.md` = `@AGENTS.md`** import (Claude reads only `CLAUDE.md` — confirmed in Claude Code docs). Keep **<~200 lines** (Claude pays full content every turn). |
| **2. Procedural (per-agent)** | the workflow | on trigger | a per-agent adapter — Claude **Skill** / Cursor **rules** / Copilot **instructions**. Description always-on (cheap), body on use. **Optional.** |
| **3. Live state** | fresh `outdated`/`diff` | on demand | `zib outdated`/`zib diff` output, or a `SessionStart` hook injecting it. Zero always-on cost. |
| **FLOOR. Self-describing CLI** | *the substance* | always | the CLI's **stdout IS the context**; any agent drives it with zero priming via general CLI competence. Universal. |

**Load-bearing principles:**
- **Determinism lives in the CLI + repo state, never in delivery.** Delivery is the *agent's*
  behavior — uncontrollable, same boundary as "zib never executes." Don't try to make it deterministic.
- **Dumb-tool split:** zib provides menus / templates / self-describing output; the agent detects
  its env and acts. **zib never detects the agent.**
- **Correctness rests on the verify/confirm gate, not on delivery.** A blind agent's mistakes are
  caught by evals + `confirm`; perfect priming is an accelerant, never a prerequisite.
- **Adapters are disposable plugins over the stable CLI port** (microkernel framing; cf. D1
  hexagonal). New framework → one adapter, kernel untouched. Selection is **static at install**,
  not clever at runtime. **No MCP server for v1** (always-on tool-schema bloat).
- **The floor is the default branch:** unknown env → `AGENTS.md` + CLI; setup must never hard-fail.

**Scope guard.** This is "zib ships a setup guide + adapter templates, like any good package" —
*not* the recursive "zib manages its own delivery plugins as zib-references" idea (circular;
rejected for v1, cf. the microkernel discussion).

**Code touch-points (when ratified):** refactor `ensure_claude_import` (write block → `AGENTS.md`;
`CLAUDE.md` = `@AGENTS.md`); make `zib init` the setup step; define the agent-facing **output
contract** for `outdated`/`diff`/`update`/`confirm` so the CLI *emits context*.

**Open threads (work these — the point of keeping this Active):**
1. **Decision-table staleness** — frameworks proliferate; how is the install-time table maintained
   and versioned without the recursive trap?
2. **Minimal always-on block** — exactly what belongs in Layer 1 vs pulled? Smallest viable pointer.
3. **Setup command shape** — is `zib init` right, or a dedicated `zib setup` / `zib agent-wire`?
   Detection + idempotency + re-wire-on-env-change details.
4. **Adapter templates** — ship in-repo or generate? One canonical Skill/rules template set?
5. **Output contract** — how self-describing must `zib` / `zib status` be to truly need zero
   priming? (ties to DS5's `outdated`/`diff` output.)
6. **Active vs passive state surfacing** — carryover from DS5: push at session start vs pull on demand.

**Built (initial, forward-looking):** the installation spec **`INSTALL.md`** (a self-contained
hand-to-any-agent bootstrap) + bundled **system references** under `src/zib/system/`
(`integration`, `usage`, `authoring`). These ship inside the package and are materialized by
`zib init` (forthcoming). CLI-dependent steps (`zib init`/`zib setup`, materialization, `--json`)
are marked **forthcoming** until `app_cli` lands.

## DS8 — Tool name: `zib` (not `hew`)

**Status:** Accepted · **Serves:** —

**Decision.** Keep the name **`zib`**. Evaluated against `hew` on a brand-name metric (meaning-fit,
distinctiveness, ambiguity, namespace collision, ergonomics, migration cost): **`zib` 26 vs `hew`
~18**. `zib` is a clean, collision-free coined name — the profile that brands well for dev tools
(Zig/Bun/Zod/Vite) — with no homophone and **zero migration cost** (it is already the package, the
`zib.ref.toml` marker, and the CLI command). `hew`'s sole advantage was meaning ("hew to" = conform
to), captured for free as the **tagline**: *"zib — hew to your references."* The Renesas "HEW"
collision was judged irrelevant (different domain); the deciding factors against `hew` were the
**hue/Hugh homophone** + migration cost.

---

## Still open

- **Surfacing UX** — does any package manager surface change info *actively* at upgrade time,
  or always passively (consumer must go find it)? Decide zib's posture. (DS5)
- **Advisory / yank channel** — security-advisory feeds (OSV/GHSA, RustSec, Dependabot) and
  yank/deprecate as a structured "this version is bad, and why" channel that aggregates across
  versions. Worth a focused research pass. (DS5)
- **Reconcile `examples/INSTALLING.md`** with DS2 (collapse `SOURCE.md`) and DS5 (release-change
  layers + markers). (DS6)
- **🔄 Agent-context delivery (DS7) is an ACTIVE discussion** — six open threads in DS7
  (decision-table staleness, minimal always-on block, setup-command shape, adapter templates,
  the CLI output contract, push-vs-pull state). This is the one we're actively improving.
