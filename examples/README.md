# Anatomy of a good zib package

> The decided convention for what a **zib package** contains and how it looks.
> zib enforces **none** of this — it reads only the two fields in `zib.ref.toml` and
> treats every other file as opaque, pinned prose. This is the *producer's discipline*.
> The reference exemplar lives in [`packages/acme-orders/`](packages/acme-orders/).
>
> For the deep design of the **installation concern** specifically — version alignment
> between the pinned reference and the real installed library, the install→verify→confirm
> loop, and how the install anatomy flexes by reference type — see
> [`INSTALLING.md`](INSTALLING.md).

---

## What a zib package is

An ordinary git repo (tagged per release) whose pinned tree is **deliberately curated
for an AI agent to read**. It is a **reference**, not a dependency: you read or run it to
learn *how to use* a thing — you do **not** ship the thing itself. The library/product is
installed from its own registry (pip/npm/cargo); the package *points to* it.

The deciding test for any file: *is this something the agent reads or runs **to
learn/verify**, or is it the **thing run in production**?* Learn/verify → ship it.
Run in production → it's a dependency; point to it.

---

## The layout (product / library package)

```
acme-orders/                  # a published package = its own tagged git repo
├── zib.ref.toml              # REQUIRED  the marker zib parses: description + suggested_role
├── OVERVIEW.md               # REQUIRED  the entry map — read first, links to everything
├── INSTALL.md                # deps/libraries, env, install, verify step
├── USAGE.md                  # the "how" — core tasks, in order of likelihood
├── API.md                    # the public surface to call (GENERATED from source)
├── SOURCE.md                 # pointers into the real repo, commit-pinned
├── PITFALLS.md               # the sharp edges — what bites people
├── RELEASES.md               # per-version notes — the delta's "intent layer"
├── examples/                 # runnable, assertable golden examples
│   ├── 01-place-order.py
│   └── 02-handle-webhook.py
└── evals/                    # the agent runs these to self-verify, then `zib confirm`
    ├── smoke.py
    └── README.md
```

### Required vs optional

| File | Status |
|---|---|
| `zib.ref.toml` | **required** (the marker) |
| `OVERVIEW.md` | **required** (one-screen orientation) |
| `INSTALL.md`, `USAGE.md`, `API.md`, `examples/`, `RELEASES.md` | strongly recommended for a product/library |
| `SOURCE.md`, `PITFALLS.md`, `evals/` | optional, high value |

### It flexes by reference type

A **pure spec/convention** reference (an OpenSpec spec, an OTLP doc) collapses to
`zib.ref.toml` + `OVERVIEW.md` + the spec content + `RELEASES.md` — no
`INSTALL`/`API`/`SOURCE`/`examples`, because there's nothing to install, call, or point
into. Same convention, sized to the thing.

---

## The three principles that make it *ideal for zib*

1. **One concern per file, stable filenames.** zib's whole value is the delta. Split by
   concern so a changed install step diffs `INSTALL.md` *only* and a new function diffs
   `API.md` *only*. One giant `README` produces muddy diffs and buries the change — the
   exact failure zib exists to prevent. Renaming files between versions breaks diff
   alignment; treat filenames as a contract.
2. **Generated from source, never hand-asserted** — for anything mirroring code (`API.md`,
   `SOURCE.md` pointers, dep versions). Hand-written surface docs rot; generated ones can't.
   Make it a release-time build step.
3. **Progressive disclosure.** `OVERVIEW.md` is a one-screen map; everything else is
   reachable from it; the agent reads only what the task needs (zib's own *select & read,
   never bulk-read* rule).

---

## Ship / point-to

| Ship it (reference) | Point to it instead (dependency / artifact) |
|---|---|
| Prose: OVERVIEW, USAGE, API, INSTALL, PITFALLS | the library's own source → `SOURCE.md` + `pip install` |
| Runnable examples / golden evals (small text) | a full demo app / starter repo → link it |
| Tiny smoke/eval harness | **binaries: wheels, images, models, datasets** → a registry |
| Config templates, JSON Schemas, fixtures | generated build output → regenerate, don't commit |

**Binaries defeat zib's point**: the delta is tree-to-tree text; a binary can only be
reported "binary changed," which destroys the "show me exactly what changed" guarantee.

---

## Size budget

Not disk (that's free) — the limits that matter:

- **Agent read budget:** readable in one session — **llms.txt scale: tens of KB of text,
  low hundreds at most.** Megabytes means you're vendoring something you should point at.
- **Diff legibility:** small single-concern files diff cleanly; vendored trees flood the delta.

Runnable examples/evals essentially never make a package too big — they're a few KB each
and are the highest-value content you can ship (the agent runs them → `zib confirm`).

---

## How the agent consumes it

| Step | Reads | Mechanism |
|---|---|---|
| Select | `zib.ref.toml` description + inventory | pick the right reference |
| Orient | `OVERVIEW.md` | one screen, then jump by task |
| Apply | `USAGE.md` + `API.md` + `examples/` | write conforming code |
| Verify | `evals/` | agent runs them, self-checks → `zib confirm` |
| Go deep | `SOURCE.md` | follow pinned pointers out-of-band |
| Keep current | `RELEASES.md` + per-file diff | concern-per-file → precise "what changed" |
| Remember | the consumer's `notes.md` | project-specific usage — **not** in the package |

> **zib never executes anything.** Examples and evals are run by the *agent*, with its own
> runtime and judgment. Shipped runnable code should be dependency-light and treated as
> untrusted (it came from a producer), same as any remote dependency.

---

## The quality bar — ideal vs. adequate

- ✅ Orient in **one screen**; everything reachable from `OVERVIEW.md`
- ✅ **One concern per file**, filenames stable across versions
- ✅ Surface / deps / pointers **generated from source**
- ✅ Examples **runnable with assertable outcomes** (real evals, not snippets)
- ✅ Source pointers carry a **commit** (reproducible "go look")
- ✅ **Describes, never restates** — points to source instead of copy-pasting; leaves
  project-specific usage to the consumer's `notes.md`
- ✅ **Sized to the slot** — readable in one session, deep enough to rarely need the raw repo
- ✅ `RELEASES.md` per version, headings `## vX.Y.Z`
- ❌ one giant README · ❌ vendored source dumps · ❌ hand-maintained API lists ·
  ❌ binaries · ❌ renamed files each release
