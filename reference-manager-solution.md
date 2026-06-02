# Reference Manager — Final v1 Solution Spec (build-ready)

> **Name:** **zib** — typed constantly as a command (`zib add`, `zib update`, `zib diff`); config files `zib.toml` / `zib.lock`. Verified clean: no prominent software / dev-tools / AI product, company, or OSS project shares the name.
>
> **Companion to the intent doc** (`reference-manager-intent.md`). The intent doc says *what* and *why* and **governs**; this doc says *how*. If they ever disagree, intent wins and this is corrected. Build exactly what is specified — no more (intent §2: include nothing the problem doesn't require). Where this spec is silent, take the simplest interpretation that adds no new concept, command, or file format, and note the choice in a comment.

---

## 1. Scope of v1, and what is settled

This spec realizes the four needs in the intent doc — **reuse, swap, update-with-delta, customize** — for references that live in **git repositories** (GitHub, GitLab, Bitbucket, self-hosted, or a local git repo). The defining decisions, all settled:

1. **Upstream is git — any git remote, not just GitHub.** The `git` CLI gives the delta everything it needs on *any* host: the tag (and branch) list, an immutable commit to pin to, and the exact diff between any two commits. Host APIs (e.g. GitHub/GitLab Releases) are *optional enrichment* for richer notes — never the foundation. Fetching sits behind a thin **source-adapter seam** (§6) so non-git upstreams can be added later as adapters, not rewrites; **v1 ships the git adapter only** (§12).
2. **Everything pins to a commit.** A version constraint, an exact tag, a branch, or a SHA all resolve to one immutable commit, recorded in the lockfile. The ref type only changes *how `update` re-resolves* and *what flavor of delta you get* — not reproducibility, which is always commit-pinned, anchored by the exported-tree hash.
3. **The delta is computed primarily as a diff between two pinned commits**, with the producer's release notes (for tag/semver refs) or the commit log (for branch refs) layered on as intent, and a **"this is a rewrite, re-read the whole thing"** escape hatch when the change is too large to be a meaningful increment.
4. **A reference can track a release *or* a branch.** Tag/semver refs give release-style deltas (version list + notes + diff). A **branch** ref is a *tracking* mode for unreleased/experimental specs (commit-log + diff); the pin still advances only on explicit `update`, and the reference is flagged provisional (§6, §9).
5. **The tool never reads or judges the consumer's codebase.** It fetches, pins, stores, surfaces, and diffs. Applying a reference to code is the agent's job; *whether the code conforms* is the agent's assertion (§9.3), never something zib verifies.
6. **The consumer's coding agent is the runtime.** The user talks only to the agent; the agent **installs** (materializes), **applies** the specs to code, **confirms** conformance, and maintains each reference's `notes.md`. zib is agent-accessible via the CLI + a zib-maintained `AGENTS.md` block (bridged into `CLAUDE.md`) + one focused skill + a `SessionStart` poll hook (§11). zib pins/diffs deterministically; the **agent supplies the intelligence** — resolving a named spec to a repo, finding/evaluating alternatives for a role — so zib needs no spec registry.

---

## 2. The model — six concepts

| Concept | What it is |
|---|---|
| **Reference** | An external thing the project depends on, at a pinned commit, living in a git repository. Self-describing, swappable, version-bumpable. |
| **Role** | A short label naming the *need* a reference fills (the "slot"). Enables grouping and swapping-within-a-slot. (Two references sharing a role are alternatives.) |
| **Manifest** | `zib.toml` — declared intent: which references fill which roles, from which git sources, at what ref/version. Hand-edited. |
| **Lockfile** | `zib.lock` — tool-written pinned reality: the resolved ref, the **pinned commit**, content hashes, and the agent's **conformance baseline**. For reproducibility and correct deltas. |
| **Notes** | `notes.md` — per-reference freeform prose: the project-specific usage. The only thing the consumer authors (in practice, the agent writes it on the user's instruction). |
| **Delta** | What changed between the code's conformance baseline and the current pin, surfaced so the agent acts on it. |

There is **no** problem-statement concept (the reference self-describes), no composition, and no two-tier customization in v1 (§12).

---

## 3. On-disk layout

```
<project-root>/
├── zib.toml                       # manifest (declared intent; hand-edited)
├── zib.lock                       # lockfile (pinned reality; tool-generated)
├── AGENTS.md                      # zib maintains a marked block (agent protocol + inventory); rest is the user's
├── CLAUDE.md                      # zib ensures a one-line `@AGENTS.md` import (Claude Code bridge)
└── .zib/
    └── references/
        ├── <reference-name>/
        │   ├── <version>/             # fetched tree of the pinned commit (immutable; self-describing)
        │   │   ├── …files…
        │   │   ├── zib.ref.toml        # OPTIONAL: producer metadata (one-line description, suggested role)
        │   │   └── RELEASES.md         # OPTIONAL: producer release notes (if present in the repo)
        │   ├── <baseline-version>/     # retained for offline deltas (see Retention, §10)
        │   └── notes.md                # OPTIONAL: project usage (agent-authored on the user's instruction)
        └── …
```

- **Everything is committed to version control.** The tool never depends on state harder to recover than a git commit (intent §3.1). A fresh clone already has `.zib/references/` — `install` then verifies, rarely fetches.
- **Content lives under `.zib/`** (namespaced under the tool's own dir, like `.cursor/rules/` and `.github/`) rather than grabbing a generic top-level name. The manifest and lockfile stay at the repo **root** (idiomatic for package-manager config). `zib.toml`/`zib.lock`, `AGENTS.md`, `CLAUDE.md`, and `.zib/` are the only paths zib writes.
- A version directory is named for the resolved ref label (a tag like `2.1.3`, or for a branch `main@4f3a9c2`, so successive branch pins don't collide).
- Content under `<version>/` is the **tree of the pinned commit**, with **no VCS metadata** (no `.git/`) and **no line-ending normalization** — see §6. Immutable from the consumer's perspective; customization happens only in `notes.md`.
- `RELEASES.md` / `zib.ref.toml`, if present, are the *producer's* files, part of fetched content — read verbatim, never authored by zib.
- `notes.md` is the *consumer's* prose — stored and surfaced, never parsed, validated, or enforced.
- **No `.trash/`.** Removal recovery is git history itself (`git revert`/`restore`/`reflog`) — never depend on state harder to recover than a commit (intent §3.1), so a separate trash layer is redundant.

---

## 4. The manifest (`zib.toml`)

TOML — the idiomatic format for a hand-edited dependency manifest (cf. Cargo.toml, pyproject.toml, uv), typed and free of YAML's hand-edit footguns. Carries only declared intent.

```toml
# zib.toml — declared intent (hand-edited)

[[references]]
name        = "openspec"                 # required, unique, [a-z][a-z0-9-]*
role        = "spec-driven-development"   # required; the slot this fills (short free-form label)
git         = "openspec/openspec"         # required; owner/repo (GitHub), a full git URL, or a local path
version     = "^2.1.0"                     # semver range | exact tag | "latest"
description = "Our spec-workflow source of truth"   # optional; one-line selection label

[[references]]
name = "dozer"
role = "json-mapping"
git  = "https://gitlab.com/acme/dozer.git"   # any git remote, not just GitHub
tag  = "v7.4.0"                              # an exact tag (alternative to version)

[[references]]
name         = "otlp-draft"
role         = "telemetry-spec"
git          = "open-telemetry/opentelemetry-specification"
branch       = "main"                        # track a BRANCH (provisional/experimental); see §6/§9
subdirectory = "specification"               # optional in-repo subpath

[poll]                                       # optional; the polling policy (§8.4)
on_update = "report"                         # report (surface only) | pull (auto in-range `update`; never `upgrade`, never applies code)
interval  = "24h"                            # cadence for the SessionStart hook / scheduled trigger
scope     = "all"                            # all | a list of reference names
```

Field rules:
- **`name`** — primary key; the content dir, notes, and lockfile entry are all keyed off it.
- **`role`** — required short label naming the need filled. References sharing a role are alternatives for the same slot (the swap-set). Free-form; the set of roles is just the union of labels.
- **`git`** — the git source: `owner/repo` (resolved against GitHub), a full git URL (`https://…`, `git@…:…`, `….git`), or a local git-repo path. Normalized to a full host-qualified URL at `add` time and persisted, so the committed coordinate is host-explicit. Only source type in v1 (§12).
- **the ref keys** — exactly **one** of: `version` (a **semver range** `^2.1.0`, an **exact tag**, or `"latest"`), `branch` (track a branch tip), `tag` (an exact tag — same effect as putting a tag in `version`, but explicit), or `rev` (a commit SHA, frozen). These mirror Cargo/Poetry/uv (`git` + `branch`/`tag`/`rev`) and are **mutually exclusive** — a manifest carrying two is a parse error.
- **`subdirectory`** *(optional)* — an in-repo subpath (the Poetry/uv key for exactly this), in case the reference is one folder of a larger repo.
- **`description`** *(optional)* — a one-line label used purely for *selection* in `list` and the agent inventory (§11). **Cascade:** this manifest field wins if set; else the producer's `zib.ref.toml` `description`; else `name · role`. A selection aid, **not** a restatement of the reference (P1).
- **`poll`** *(optional, top-level)* — the polling policy (§8.4).

The reference's own content carries its full self-description; the manifest never duplicates it.

---

## 5. The lockfile (`zib.lock`)

TOML, tool-generated, committed. The receipt of what's actually pinned, plus the agent's conformance baseline. **Never hand-edited** (only `zib confirm` writes the one agent-asserted field).

```toml
# zib.lock — pinned reality (tool-generated)
lockfile_version = 1

[references.openspec]
ref_type        = "semver"                  # semver | tag | branch | commit  (how `update` re-resolves)
resolved        = "2.1.3"                    # display-only label; names the content dir; NEVER an operand
resolved_commit = "4f3a9c2e…"                # the pin — full 40-hex commit SHA (the git refetch id)
content_hash    = "sha256:…"                 # over the EXPORTED TREE of the pin (reproducibility anchor + integrity)
confirmed_through = { commit = "9b1e077…", content_hash = "sha256:…" }   # conformance baseline; omitted = nothing confirmed
```

- **The pin is two parts** (precedent: Nix fixed-output derivations, Go `go.sum`): `resolved_commit` is the **git-native refetch id** (immutable where a tag/branch is not), and `content_hash` is the **source-agnostic reproducibility anchor** — a hash of the *exported tree*, which is what actually guarantees identical bytes (`git archive` bytes are *not* reproducible across git/compressor versions). Future non-git adapters won't have a commit SHA but will still produce a `content_hash`.
- **`ref_type`** — how `update` re-resolves: `semver`/`tag` → a (possibly higher) satisfying tag; `branch` → the branch's current tip; `commit` → frozen. Also flags branch refs as provisional in `list`/`info`.
- **`content_hash`** — SHA-256 over the version directory, canonicalized (§13): recursively list files sorted by raw UTF-8 path bytes, include each entry's mode, hash symlink targets (never dereference), NFC-normalize paths, ignore empty dirs; encode `sha256:<hex>`. Deterministic, verifiable **offline**; both the reproducibility anchor and the integrity check (§7).
- **`confirmed_through`** — **the conformance baseline**: a `{ commit, content_hash }` pair the agent has **confirmed the code conforms to** (§9.3). The `commit` is an **immutable SHA captured at confirm time** (never a re-resolvable label, so a moved/deleted tag can't reinterpret a past conformance claim); the `content_hash` integrity-checks the retained baseline tree. Omitted = nothing confirmed yet (first encounter ⇒ `zib cat`). **Written by zib only via `zib confirm`** (preserving "tool-generated, never hand-edited"); zib **never derives it from code** — it records the agent's assertion, which the tool cannot verify.
- **Deliberately NOT in the lockfile:** `role` / `git` / `subdirectory` / `version` (declared intent — live in `zib.toml`, co-committed); the original constraint (`requested` — drift is computed live, §10); timestamps (never a decision input; recoverable from git commit times — and their removal makes idempotency trivial, §10).

---

## 6. Sources, refs, and fetch (git)

**The source (only kind in v1): a git remote.** Everything uses the **`git` CLI**, so it behaves identically across GitHub/GitLab/Bitbucket/self-hosted/local. **Auth is whatever the user's git already uses** (SSH keys, credential helpers, tokens) — zib shells out and never handles credentials.

**Ref types — all resolve to one commit:**
- **`version` semver range / `"latest"`** — matched against the repo's tags. Requires semver-parseable tags; a non-semver tag under a range/`latest` is an `unresolvable version` error (§10).
- **`version`/`tag` exact tag** — that tag.
- **`branch`** — the branch's current tip. *Tracking mode:* provisional; `update` advances the pin to the new tip, delta is commit-log-driven (§9). Flagged provisional in `list`/`info`.
- **`rev` commit SHA** — that commit, **frozen** (never auto-updates).

**Resolution + fetch:**
1. **Resolve the ref to a concrete commit.** semver/`latest` → enumerate tags (`git ls-remote --tags <git>`), **dereference annotated tags to the underlying commit** (read the `^{}` peel line — do *not* pass `--refs`, which suppresses it), pick the highest satisfying → its commit. exact tag → its commit; branch → its tip commit; SHA → itself. Record the human label in `resolved` and the kind in `ref_type`. If a previously-resolved tag now points to a **different** commit (moved tag), surface it as a supply-chain signal — do not silently re-pin.
2. **Record the commit SHA as `resolved_commit`.** This is the pin — for every ref type.
3. **Export the commit's tree** (restricted to `subdirectory` if given), **raw blob bytes, attribute-blind** — no `.git/`, line-ending normalization off, and `.gitattributes` export directives (`export-subst`/`export-ignore`/`eol`/`text`) **disabled**. Use plumbing (`read-tree` into a throwaway index + `checkout-index -a`, or per-blob `cat-file`) with `core.autocrlf=false`/`core.eol=lf`, then strip `.git/`. The pinned bytes are the producer's committed blobs; the only thing that varies them is the commit SHA. **Reproducibility is anchored on the `content_hash` of the resulting tree — not on `git archive` bytes.**
4. **Compute and record `content_hash`.**

After the first resolve, every fetch is by `resolved_commit`; the mutable ref (tag/branch) is consulted only by `update`/`upgrade`/`outdated`.

**The source-adapter seam (thin).** All of the above lives behind one internal interface:

```
resolve(ref)         -> commit      # MANDATORY: constraint/tag/branch/sha → immutable commit
fetch_tree(commit)   -> tree        # MANDATORY: the pinned content (zib computes its content_hash)
list_versions(range) -> [version]   # optional: authoritative version enumeration (git supplies it)
notes(version)       -> prose|none  # optional: producer notes (git supplies via RELEASES.md / host API)
```

zib computes the **diff itself** from any two fetched trees — so `diff` is *not* an adapter method (any source that can `fetch_tree` can be diffed). v1 ships exactly one adapter — **git** — supplying all four. A future URL / registry / unversioned-local adapter implements `resolve`+`fetch_tree` (and optionally the rest) and slots in; where it can't supply `list_versions`/`notes`, the delta degrades to the §9.2 "re-read the whole reference" mode. (Capability-negotiation machinery is deferred until a real second adapter needs it — §12.)

---

## 7. Integrity & reproducibility

- **Reproducibility is anchored on committed content + the exported-tree `content_hash`.** Because `.zib/references/` is committed, a teammate's fresh clone already has the exact bytes — nothing is fetched, no upstream needed. When a fetch *is* needed (first install of a new pin, or content missing), zib fetches by the immutable `resolved_commit` and **verifies the exported tree against `content_hash`**.
- **Refetch is best-effort, stated honestly:** committed `refs` content is the floor. Tag/semver commits are tag-reachable → refetchable on any host. Branch/`commit` SHAs may be unfetchable on locked hosts or after upstream GC; in that case the **committed bytes are authoritative** (verified by `content_hash`), and an irrecoverable mismatch is a hard warning — branch refs carry this weaker guarantee by nature (intent §4, "provisional").
- **`content_hash` doubles as the offline integrity check** over **every retained tree** (the pin *and* the `confirmed_through` baseline). On install/diff, a mismatch → warn; prefer the committed tree when its hash re-derives, refetch by commit only as fallback, hard-error only if a pinned commit is unreachable upstream.
- **`install` behavior:** content present + hash matches → verify-only **no-op** (lockfile not rewritten — §10 idempotency); content missing → fetch by `resolved_commit`, verify; hash mismatch → warn + refetch by commit.

---

## 8. CLI surface

Verb-first (`zib <verb>`), like cargo/git/npm. Flags are kebab-case long form; `--json` on every data-returning command; `--help`/`-h` everywhere; `--version`/`-V` (lowercase `-v` reserved for `--verbose`).

| Command | Purpose |
|---|---|
| `zib init` | Scaffold `zib.toml` + `.zib/`, the agent files (a marked `zib` block in `AGENTS.md` + a `@AGENTS.md` import in `CLAUDE.md`), and the focused skill (§11). Fail if the manifest exists. |
| `zib add <name> --role <r> --git <src> [--version\|--branch\|--tag\|--rev] [--subdirectory] [--yes]` | Add a reference, resolve + pin + install, create empty `notes.md`. `--yes` required when an agent confirms a self-resolved source (§11). On install failure, the manifest entry is rolled back (no orphan). |
| `zib install` | Install all manifest references at locked commits (fetch by pinned commit only when missing); verify hashes; **report drift** (§10); idempotent. |
| `zib outdated [<name>] [--json] [--exit-code]` | **Read-only poll** — per reference report **current → wanted → latest** + a state. No name = all; positional names scope it. Never mutates; **exits 0** even when updates exist (opt-in `--exit-code` for CI). (§8.4) |
| `zib update [<name>]` | **In-range consume.** Re-resolve to **wanted** (newest satisfying the live `zib.toml` constraint), re-pin the lockfile, **leave the constraint untouched**, leave `confirmed_through` untouched, and **surface the delta** (§9). No name = all. |
| `zib upgrade [<name>] [--yes]` | **Jump to latest, beyond the constraint.** Move to **latest**, **rewrite the `zib.toml` constraint**, re-pin, surface the delta. The only consume that edits the manifest; **explicit + confirmed** (`--yes`). No-op for `commit` refs (frozen) and `branch`/`latest` (already newest → use `update`). |
| `zib diff <name> [--from] [--to] [--full] [--json]` | **Read-only** — surface the delta (what changed between the conformance baseline and the pin). Mutates nothing (§9.2). |
| `zib confirm <name> [--to <version\|commit>]` | **Advance the conformance baseline** — the agent asserts the code now conforms through the current pin; sets `confirmed_through` (§9.3). `--to <retained ancestor>` moves it *back* to recover an over-assertion. |
| `zib swap <old-name> <new-name> --git <src> [--version\|…] [--subdirectory] [--yes]` | Replace `<old-name>` with a new reference that **inherits its role**. Old reference + notes removed (recover via git); new reference installed with fresh empty notes, `confirmed_through` reset (§8.2). |
| `zib remove <name>` | Remove from manifest + lockfile + `.zib/references/<name>/` (recover via git). |
| `zib list [--by-role] [--json]` | Inventory: name, role, **one-line description** (§4), declared ref + resolved version, branch-provisional flag, whether the pin is **ahead of the confirmed baseline** (owed delta), whether notes exist. `--by-role` groups by slot. |
| `zib info <name> [--json]` | Detail: ref type, resolved version, pinned commit, hashes, `confirmed_through`, paths (incl. the `notes.md` path), notes preview. |
| `zib cat <name> [--json]` | Output the full agent-context bundle (§8.1) — first encounter / full context. NOT the after-update path (use `diff`). |

Every command that changes the reference set (`add`/`update`/`upgrade`/`swap`/`remove`/`install`) also **refreshes zib's marked inventory block in `AGENTS.md`** (§11) — rewriting only the block interior, never the user's surrounding content.

### 8.1 `cat` — the full bundle (first encounter / full context)

Outputs, with delimiters an agent can parse:
1. Header: name, role, resolved version (and `(branch — provisional)` if branch-tracked), pinned commit, git source, and the **`notes.md` path** (where the agent records usage).
2. `----- content -----` : every file in the version dir, each prefixed with its relative path (carries the reference's self-description).
3. `----- notes -----` : full contents of `notes.md` if present.

No filtering, no interpretation. Delimiters like `===== reference: <name> (<role>) @ <version> =====` and `----- <section> -----`, used consistently.

### 8.2 `swap` — replace the reference filling a role

Keyed on the **reference being replaced**, not the role — removing the ambiguity when two references share a role (a legitimate swap-set, §4). Swap:
- Removes `.zib/references/<old-name>/` (content + notes) — recoverable via git history.
- Adds `<new-name>` to the manifest **under `<old-name>`'s role**, resolves + pins + installs, creates fresh empty notes, sets `confirmed_through` = none.
- Updates manifest + lockfile.
- Old notes are intentionally **not** carried over (different reference, different usage — intent §3.3).

### 8.3 `update` — bump a ref (and surface the change)

`update` re-resolves within the ref's kind (higher tag for semver/tag; current tip for branch), re-pins the new commit, **retains the prior + the baseline version** (§10 retention), keeps `notes.md` unchanged, and **leaves `confirmed_through` untouched** — so `pin > confirmed_through` is exactly the "owed/unconfirmed delta" signal. It then **surfaces the delta** (§9):

```
Updated openspec: 2.1.1 → 2.1.3
  Showing delta vs your confirmed baseline (2.1.1). Apply, then `zib confirm openspec`.
  [delta output, or: run `zib diff openspec`]
```

(A `commit`-pinned ref is frozen — `update` reports nothing to do.)

### 8.4 The update workflow — poll, then consume

Three consume verbs, mirroring the universal package-manager split. The hard line everywhere is *does the declared constraint change?* — so in-range and jump-to-latest are **separate verbs** (cf. `cargo update` vs `cargo upgrade`):

| Verb | Mutates | Moves to | `zib.toml` constraint |
|---|---|---|---|
| `outdated` | nothing (read-only) | — (reports) | unchanged |
| `update` | lockfile | **wanted** (newest in-constraint) | unchanged |
| `upgrade` | lockfile + **manifest** | **latest** (newest overall) | **rewritten** (e.g. `^2.1.0` → `^3.0.0`) |

- **`outdated`** polls via `git ls-remote` (cheap; no fetch, no write), reporting **current / wanted / latest** + a state — `up-to-date`, `in-range-update`, `out-of-range-update` (needs `upgrade`), `frozen` (commit ref), `tracking` (branch/`latest`), and `pending-confirm` (pin ahead of the confirmed baseline). `--json`; exits 0 regardless of findings.
- **Ref-type interactions:** branch/`latest` refs are always-newest, so `wanted` == `latest` and `update` advances them (`upgrade` is a no-op); `commit` refs are frozen.
- **Polling is a present, first-class mechanism, built from stateless runs (no daemon):**
  - On `zib init`, zib installs a **`SessionStart` hook** that runs `zib outdated` and surfaces pending updates into the agent's session — so **every session begins knowing what's stale** (§11).
  - zib can scaffold a **scheduled CI job** (cron) that polls and reports / opens a PR for unattended freshness.
  - The **`poll:` policy** (§4) governs both: `report` (default — surface only) vs `pull` (auto-`update` *in-range*, lockfile-only). `upgrade` is **never** automatic, and a poll **never** auto-applies to code or auto-`confirm`s (those are the agent's). Each tick is a stateless `zib outdated`/`update` run invoked by the hook/cron — zib is never a persistent service.

---

## 9. The delta mechanism (CORE — correctness, not efficiency)

**Why this is core.** On an update, re-loading the whole reference buries the change in unchanged bulk and the agent misses small-but-important updates — a correctness failure (intent §1, §3.2). The agent must be oriented to *what changed*, never handed the whole. Git makes this authoritative: from the pinned commits the tool computes the exact diff, and for releases it enumerates exactly which versions exist and reads each one's notes.

### 9.1 The inputs (all from committed content + the git remote, keyed on pinned commits)

For **tag / semver** references:
1. **The version list in range** — the repo's tags in `(baseline, pin]`. Authoritative, so coverage is *known*. A jump 1 → 4 (with 2, 3 never installed) still yields {2, 3, 4}.
2. **Release notes (intent layer)** — per tag in range: the host Release body if present, else the matching `## v<version>` section of `RELEASES.md` at the pin, else "(no notes for `<version>`)".
3. **The diff (structural backbone, always available)** — computed **tree-to-tree from committed bytes**: the retained baseline tree vs the pin tree. `RELEASES.md` excluded; binaries noted "binary changed". The net diff inherently covers skipped versions, and **never requires upstream reachability**.

For **branch** references: no tag list and no release notes (1,2 absent). The delta is the **commit-range diff** plus the **commit log** between the two pins (commit subjects = the changelog for unreleased work), clearly marked a **provisional branch delta**.

### 9.2 `zib diff` — read-only

`diff <name> [--from] [--to] [--full] [--json]`:
1. **Range** = `(--from or confirmed_through.commit, --to or current pin]`, **commit-anchored** (always the immutable SHAs, never re-resolved labels). If empty, report "no unconfirmed changes," exit 0.
2. **Surface notes** (tag/semver) or the **commit log** (branch) for the range.
3. **Compute the diff** tree-to-tree from committed bytes (baseline tree vs pin tree, each integrity-checked against its `content_hash`; refetch by commit only if a local tree is corrupt). Assess magnitude: incremental → emit the unified diff; **major rewrite** (changed lines ≥ 50% of combined, or ≥ 75% of files) → emit a one-line size summary + the directive *"substantial rewrite — re-read the whole reference (`zib cat <name>`)"* (accumulated notes still accompany it). `--full` forces the diff.
4. **Append `notes.md`** for the agent to reconcile against project usage.

**`diff` mutates nothing** — it never advances the baseline, so it can be re-run (and pre-injected by the skill) freely, and it re-shows the still-unconfirmed delta until `confirm` closes it.

### 9.3 The conformance baseline & `zib confirm` (the centerpiece)

Three states per reference, separated by owner:

| State | Where | Owner | Advances on |
|---|---|---|---|
| **PINNED** | `resolved_commit` | zib (truth) | add / update / upgrade / swap |
| **SURFACED** | `zib diff` output | — (**transient, not stored**) | — |
| **CONFIRMED** | `confirmed_through {commit, content_hash}` | **the agent (assertion)** | **only `zib confirm`** |

```
add / swap        → confirmed_through = none          (first encounter ⇒ `zib cat`)
update / upgrade  → pin moves; confirmed_through UNTOUCHED   (pin > confirmed = owed delta)
diff (read-only)  → shows (confirmed_through.commit, pin]; never advances; re-shows until confirm
confirm <name>    → confirmed_through = { current pin commit, its content_hash }
confirm --to <x>  → move the baseline BACK to a retained ancestor (recover an over-assertion)
```

- The delta is **always** computed from this SHA-immutable, integrity-checked, locally-derivable baseline — so a change can never be silently dropped (surfacing isn't confirming), the baseline can never be wrong (it's a captured SHA, not a re-resolved label), and it never needs upstream.
- N updates without `confirm` accumulate into one correct widening `(confirmed_through, pin]` range — nothing is lost. A `poll: pull` that auto-moves the pin likewise never advances the baseline.
- `confirm` is **commit/pin-based** (asserts "the code conforms to *this pin*") — identical whether the agent applied an incremental delta or re-read the whole reference after a rewrite.
- `confirm` is a **trust action zib structurally cannot validate** (it can't read code); it records the agent's assertion. `list`/`info`/`outdated` word it as **"confirmed (by the agent) through X,"** never as a tool guarantee, and over-assertion is **recoverable** via `confirm --to`.

### 9.4 The conformance note (reflected in agent-instructions, §11)

A delta tells the agent what changed in the *reference*, not whether the project's code conformed to the baseline. The tool never reads the codebase — that judgment is the agent's. Agent-instructions must say: apply the delta, then `zib confirm`; if release-note migration guidance flags interaction with existing behavior, if a reference is branch-tracked (provisional), or if drift is suspected, **verify the relevant existing code** rather than blindly applying.

---

## 10. Behavioral requirements

- **Idempotency.** A clean `install` (content present, hashes match) is a verify-only no-op and **does not rewrite the lockfile**. Guaranteed by: timestamps removed from the lockfile, **canonical TOML emission**, and **compare-before-write** (write only if bytes differ). Safe for CI/retries.
- **Deterministic export.** §6 export is attribute-blind; `content_hash` uses the canonical serialization (§13). These make cross-machine byte-identity and the no-op hold.
- **Integrity over all retained trees.** Verify the pin tree *and* the `confirmed_through` baseline tree against their hashes; on mismatch prefer the committed tree if its hash re-derives, else refetch by commit, else hard-error (pinned commit unreachable upstream).
- **Two drifts, distinct:**
  - **Content drift** (committed bytes ≠ `content_hash`) → warn + refetch by commit.
  - **Constraint drift** (the locked pin no longer satisfies the **live** manifest constraint) → `install` **REPORTS** it ("constraint changed; run `update`/`upgrade` to re-pin") and **never silently re-pins**. Computed from `(live constraint, locked pin)` only — needs no stored original constraint. Changing a version is always `update`/`upgrade`'s job.
- **Pin-move invariant.** The pin moves *only* via add/update/upgrade/swap. None of them touches `confirmed_through` except the resets on add/swap.
- **Branch pins survive upstream rewrites.** A force-pushed/orphaned commit is still served from committed bytes; refetch-by-commit failure warns, never errors.
- **Recoverable removal.** `remove`/`swap` delete content; recovery is git history. (No `.trash/`.)
- **Retention.** Keep **current + immediately-prior + the `confirmed_through` baseline tree** (a union, bounded; one extra tree per reference whose baseline lags). The baseline tree is kept until the next `confirm` advances the floor, so `diff` is always offline-computable and `confirm --to` always has its one-step-back target.
- **Graceful degradation.** Prefer surfacing/continuing over refusing. Reserve loud failure for deterministic faults: manifest parse errors (incl. two mutually-exclusive ref keys), persistent hash mismatch, unresolvable versions, network failure after retries.
- **Output.** stdout = data only (so `list`/`cat`/`diff` pipe); stderr = progress/logs/prompts. `--json` on every data-returning command. Honor `NO_COLOR`; auto-disable color/spinners/prompts when stdout isn't a TTY. `--no-<flag>` negates default-true booleans.
- **The tool never reads the consumer's codebase.** `install` materializes spec *content*; *applying* and *confirming* are the agent's. zib reads/writes only `zib.toml`, `zib.lock`, `.zib/`, and its marked block in `AGENTS.md`/`CLAUDE.md`.
- **Agent-file maintenance is idempotent and non-destructive** — see §11/§13.

---

## 11. Agent integration

**The split:** the user talks only to the agent; **zib is the deterministic hands** (resolve → pin → install → diff → swap, plus an inventory); **the agent is the brain** (turn intent into a git source, evaluate alternatives, write code, confirm, maintain notes). zib never discovers, ranks, or applies — which is why it needs no registry.

### 11.1 The surface

1. **CLI** — the agent shells out to `zib`. The substrate.
2. **A zib-maintained block in `AGENTS.md`** (the cross-agent instructions standard). zib owns one marked, versioned region — `<!-- BEGIN zib v1 --> … <!-- END zib -->` — and rewrites **only its interior** on any reference-set change, preserving everything outside (§13). Short (<~50 lines): the protocol + the **inventory** (`name · role · description`, *no content*).
3. **`CLAUDE.md` bridge** — Claude Code reads `CLAUDE.md`, not `AGENTS.md`, so zib ensures a one-line `@AGENTS.md` import.
4. **One focused skill** (`.claude/skills/zib/`) — for the after-update review, using dynamic injection (a `` !`zib diff <name>` `` line that pre-runs zib and **inlines the delta**). Thin over the CLI.
5. **A `SessionStart` hook** (`zib init` scaffolds it) — auto-runs `zib outdated` so the agent sees pending/owed updates each session (§8.4).

The CLI + AGENTS.md block are load-bearing; the CLAUDE.md import, skill, and hook are conveniences carrying **no protocol the block doesn't state** (single source of truth = the block). MCP is deferred (§12).

### 11.2 The agent protocol (carried by the AGENTS.md block)

**Select & read (never bulk-read):** `zib install` on session start; find the relevant spec from the **inventory** (`name · role · description`) or `zib list --by-role`, matched to the user's instruction; then `zib cat <name>` **only the chosen** reference. Treat `notes.md` as authoritative; don't restate the reference. (First-encounter `cat` is keyed to *per-session* state — "haven't cat'd this yet this session" — not to any lockfile field.)

**Apply, confirm & remember:** apply the spec by writing conforming code; then **`zib confirm <name>`** to advance the conformance baseline. When the user states a durable usage decision, record it in `notes.md` (edit the file directly; `cat`/`info` print the path — there is no `zib note` command).

**Keep current (poll → consume → apply → confirm):** the `SessionStart` hook surfaces pending/owed updates; for an in-range update `zib update <name>`, for a beyond-constraint jump **propose to the user then `zib upgrade <name> --yes`**; then `zib diff <name>`, apply, `zib confirm`. If `diff` flags a major rewrite, `zib cat` fresh, apply, confirm.

**Install a named/new spec:** resolve the canonical repo (knowledge + web), **propose repo + version to the user**, then `zib add <name> --role <r> --git <repo> … --yes` → `cat` → apply → confirm.

**Find a better spec for a role:** `zib list --by-role`, research alternatives, **propose; on confirmation** `zib swap <old> <new> --git <repo> --yes` → `cat` → apply → confirm.

**Confirmation rule:** the agent must get the user's sign-off (`--yes`) before any `add`/`swap`/`upgrade` of a source **it resolved itself**; installing/updating what's already pinned needs none.

### 11.3 The instructions block zib writes (`examples/agent-instructions.md`, and what `init` writes between the markers)

```markdown
<!-- BEGIN zib v1 — managed by zib; edit only OUTSIDE these markers -->
## Managed references (zib)

This project pins external specs/frameworks/standards with the `zib` CLI. zib installs
the *content*; YOU apply it to code, then `zib confirm` it; you maintain each reference's notes.

Inventory — pick by matching the user's need to a description; then `zib cat <name>`:
{name · role · description — one line per reference, regenerated by zib}

Protocol:
- `zib install` on session start to materialize pinned specs.
- Select from the inventory above, then `zib cat <name>` to read the chosen spec + its notes
  (once per session). Do NOT read every spec to find the relevant one.
- Treat .zib/references/<name>/notes.md as authoritative for how we use a spec; don't restate it.
- When the user states a durable usage decision, record it in that notes.md (edit the file).
- After an update, `zib diff <name>` shows what changed; apply it, then `zib confirm <name>`
  (notes/commit-log first, then the diff; verify existing code; if it's a major rewrite, `zib cat` fresh).
- To take updates: `zib outdated` shows current/wanted/latest; `zib update <name>` in-range, or
  PROPOSE then `zib upgrade <name> --yes` to jump to latest (rewrites the constraint).
- To add a named spec or find a better one for a role: resolve the repo, PROPOSE it, then
  `zib add`/`zib swap … --yes` only after the user confirms.
<!-- END zib -->
```

---

## 12. Deferred — do NOT build in v1 (confirm before adding)

- **Non-git upstreams** (plain HTTP URL/archive; package registries npm/PyPI/OCI; a bespoke reference registry; an unversioned local "workspace" dir). Each sits behind the §6 seam and becomes a new adapter, never a rewrite. v1 ships git only — which already spans GitHub/GitLab/Bitbucket/self-hosted/local, with tag *and* branch refs.
- **Capability-negotiation machinery** in the adapter seam — add when a real second adapter actually lacks a capability.
- **Problem-statement layer** — references self-describe.
- **Two-tier customization** — one `notes.md`; the survives-on-update / resets-on-swap asymmetry suffices.
- **Composition** (cross-reference conflict/precedence) — only if references actually conflict.
- **Producer tooling** — publish by structuring a git repo conventionally (content + optional README + optional `RELEASES.md`, tagged per release; optional `zib.ref.toml` with a one-line `description` + suggested `role`). No producer commands.
- **Role-definition-as-reusable-artifact / controlled role vocabulary** — a role is a free-form label.
- **MCP server & skill-marketplace auto-install** — v1 uses the CLI + AGENTS.md block + one scaffolded skill + the `SessionStart` hook.
- **Spec discovery / a reference registry** — the **agent** is the discovery layer; zib pins what the agent (with the user's confirmation) chooses. A curated index is later.
- **A hosted auto-PR *service* & rich update-strategy matrices** — zib ships the polling mechanism (the `SessionStart` hook, an optional CI scaffold, the `report`/`pull` policy); the hosted PR service and widen/replace/lockfile-only matrices stay out.
- **`zib watch` and `zib clean`** — cut. The hook + optional CI cron cover every cadence the model needs (and `watch -n zib outdated` is an OS primitive); retention is bounded automatically so a configurable trim knob is unused.
- **`verify-applied` / any code-reading conformance check** — `confirmed_through` is and stays the agent's assertion; zib must never read code to validate it.
- **A second code-package manager** — this manages non-code references; it complements language package managers.

---

## 13. Implementation guidance

- **Language/runtime:** implementer's choice. Python (`pipx`/PyPI, 3.10+) or Go/Rust (static binaries) recommended; install name = command = `zib`.
- **Dependencies:** a TOML parser, a semver library, and the **`git` CLI** — ref resolution (`ls-remote --tags` / `ls-remote refs/heads`, deref `^{}`), commit pinning, attribute-blind tree export, commit-to-commit diffs. Host release APIs are optional enrichment; everything must work with `git` alone on any remote.
- **Export (one normative method):** materialize raw blob bytes via plumbing (`read-tree` + `checkout-index -a`, or per-blob `cat-file`) with `core.autocrlf=false`/`core.eol=lf` and `.gitattributes` export directives disabled; strip `.git/`. Never rely on `git archive` bytes for the hash.
- **`content_hash` canonical serialization:** over the exported tree — sort entries by raw UTF-8 path bytes; include each file's mode (100644/100755/120000); for symlinks hash the target string (don't dereference); NFC-normalize paths; ignore empty dirs; SHA-256 → `sha256:<hex>`. Pin this under the `lockfile_version` contract (it must be stable across tool versions).
- **Diff:** tree-to-tree over the two retained committed trees (refetch a missing/corrupt one by commit; two independent shallow fetches, no common ancestor needed); skip binaries; exclude `RELEASES.md`; use `git diff --shortstat` + rename detection for the §9.2 rewrite check.
- **Notes (host-agnostic first):** prefer in-repo `RELEASES.md`/`CHANGELOG.md` and annotated-tag messages (`git for-each-ref --format='%(contents)'`); host Release API only as optional enrichment. Split `RELEASES.md` on `^##\s+v?<version>` headings; don't interpret Keep-a-Changelog subsections.
- **Lockfile writes:** canonical/stable TOML emission + compare-before-write (idempotency). `confirmed_through` is written **only** by `zib confirm`.
- **Constraint-drift check:** "does the locked pin still satisfy the live manifest constraint?" — a function of `(live constraint, locked pin)`; no stored original constraint.
- **Agent files (zib-maintained):** own one `<!-- BEGIN zib v<semver> -->`…`<!-- END zib -->` block in `AGENTS.md`; on every reference-set change rewrite **only** the interior (protocol + `name · role · description` inventory) and bump the stamp — **preserve all content outside the markers**; detect-and-heal absent / duplicate / malformed markers and a removed `@AGENTS.md` import. Ensure the one-line `@AGENTS.md` import in `CLAUDE.md` (prefer import over symlink — Windows). HTML-comment markers are stripped from agent context (zero token cost). No standalone "sync" command — this is internal to the reference-set commands.
- **The skill:** scaffold `.claude/skills/zib/SKILL.md` with valid frontmatter (`name`, `description`, `allowed-tools`); use `` !`zib diff <name>` `` dynamic injection. Thin over the CLI.
- **`zib.ref.toml` (producer, optional):** read `description` verbatim (+ a suggested `role`); never scrape prose for a description.
- **Startup:** `list`/`info` < 100ms; `install` with no work < 500ms.
- **Tests:** manifest parse incl. **mutually-exclusive ref-key rejection**; ref resolution (semver/tag/`latest`/`rev`/branch; non-semver rejection under range/`latest`; moved-tag signal); commit pinning + **cross-machine byte-identity** (attribute-blind export; canonical hash; multi-host); install idempotency (clean no-op doesn't rewrite the lockfile); **constraint-drift report without a stored constraint** (widen/narrow/loosen cases) + content-drift; **conformance state machine** — `confirm` advances `confirmed_through` (SHA-captured), `diff`/`update`/`upgrade` never advance it, add/swap reset it, `confirm --to` recovers, N-updates-without-confirm accumulate one correct range, interrupted-session/fresh-clone re-surface the owed delta; **integrity over the baseline tree** (not just the pin); diff (notes incl. missing; branch commit-log; rewrite→`cat` directive; skip-versions; offline); `cat` bundle (incl. notes path); `swap` (role inherited, fresh notes, baseline reset); `AGENTS.md` block round-trip (preserve-outside, version stamp); `CLAUDE.md` import insertion; description cascade (manifest → `zib.ref.toml` → `name · role`); skill scaffold validity; `outdated` (states incl. `pending-confirm`, read-only, exit-0); `upgrade` (rewrites constraint, confirmed, no-op for commit/branch/latest).
- **Docs:** README (badges + 60-second quickstart: `init` → `add` → `install` → `cat` → `update` → `diff` → `confirm`); command reference; a "concepts" doc (the six concepts + self-describing principle); a "publishing a reference" doc; the agent-instructions template; an example project with 3–4 references across hosts incl. one branch-tracked.

---

## 14. Open-source & release conventions

Since zib ships open-source, it should follow the conventions a credible developer CLI is expected to:

- **SemVer** for the tool's own releases; `zib --version` / `-V` (optionally a `zib version` subcommand). The lockfile's `lockfile_version` is a separate format-schema integer with a Cargo-style **refuse-on-unknown** contract.
- **CHANGELOG.md** (Keep a Changelog) + **Conventional Commits** (so version bumps + changelog can be automated).
- **LICENSE: Apache-2.0** (explicit patent grant) — or the Rust-CLI idiom `MIT OR Apache-2.0`.
- **Repo hygiene:** `README.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` (Contributor Covenant), and **`SECURITY.md`** (a private vuln-report path — especially relevant since zib fetches remote git content).
- **Distribution:** Homebrew (tap → core), prebuilt GitHub Release binaries + a `curl … | sh` script, and one ecosystem registry (cargo / pipx). Install name = command = `zib`.
- **Discoverability:** `zib completion <bash|zsh|fish|powershell>` + a `zib(1)` man page; a published **JSON Schema** for `zib.toml`/`zib.lock` with an editor-validation modeline.

---

## 15. v1 success criteria

1. `init` → `add` references across **git hosts** (GitHub `owner/repo` shorthand, a full GitLab/Bitbucket/self-hosted URL, a local git repo) → `install` reproducibly.
2. **Reproducibility:** fresh clone + `install` → byte-identical `.zib/references/` (commit-pinned, attribute-blind export, canonical hash); refetch by commit reproduces the exact bytes for tag/branch/SHA refs alike; `diff`/`install` never require upstream for the baseline or pin trees.
3. `swap <old> <new>` replaces the reference, inherits the role, removes the old (recoverable via git), fresh notes, `confirmed_through` reset.
4. `update` re-resolves in-range (incl. branch-tip), re-pins, **leaves the constraint and `confirmed_through` untouched**, retains the baseline, surfaces the delta. `upgrade` jumps to latest, **rewrites the constraint**, confirmed.
5. **Conformance is airtight:** the delta is always computed from the SHA-immutable, integrity-checked, locally-derivable `confirmed_through` baseline; `confirm` (only) advances it; `diff` is read-only; surfaced-but-unconfirmed deltas re-surface across sessions/clones; N updates without confirm accumulate one correct range; over-assertion is recoverable (`confirm --to`).
6. A **branch-tracked** reference installs, pins its tip, is flagged provisional, and survives an upstream force-push (committed bytes authoritative).
7. `cat` outputs full content + notes (first-encounter path); `diff` is the after-update path.
8. `list --by-role` groups by the need filled; the inventory carries `name · role · description` and the owed-delta flag.
9. **Drift:** `install` reports content drift *and* constraint drift (no stored original constraint), and never silently re-pins.
10. **Agent integration:** `init` scaffolds the `AGENTS.md` block + `CLAUDE.md` import + skill + `SessionStart` hook; reference-set commands refresh the block interior without touching outside content; agent-driven flows (install / add-with-confirm / swap-for-role / poll→update→diff→confirm) work end-to-end.
11. The tool never reads consumer code, never asks for a problem statement, never duplicates a reference's self-description, and never verifies conformance (it records the agent's `confirm` assertion).
12. macOS + Linux. Helpful errors. New user to working install in <10 minutes from docs.

---

## 16. When this spec is silent

Prefer the simplest interpretation that adds no new concept, command, or file format. Keep the manifest lean (coordinates + role label). Keep the tool deterministic; keep notes freeform. On update, always foreground the change. **Pin the commit, not the tag or branch.** The conformance baseline is the agent's `confirm` assertion — never read code to verify it. Keep new upstreams behind the §6 seam. Outside its core files (`zib.toml` / `zib.lock` / `.zib/`), zib writes only its own marked block in `AGENTS.md` / `CLAUDE.md`. If the simplest interpretation feels wrong, flag it in a comment and ask. v1 is a small, honest tool: fetch, pin, swap, update-with-delta, confirm, customize-via-notes — over git, driven by the consumer's agent. Nothing more.
