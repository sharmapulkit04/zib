# Installing from a zib package — the producer's discipline

> Extends [`examples/README.md`](README.md) ("Anatomy of a good zib package") with a deep,
> install-focused design. Where the anatomy says *what files a package carries*, this says
> *how the install concern must be shaped* so an AI agent installs the **right real
> dependency, at a version aligned with the pinned reference, reproducibly, verifies it, and
> diffs cleanly on update.*
>
> zib enforces **none** of this. zib parses exactly two fields in `zib.ref.toml`
> (`description`, `suggested_role`) and treats every other file as opaque, pinned prose. It
> never runs an installer and never executes anything. This is the producer's discipline.
> The worked exemplar is [`packages/acme-orders/`](packages/acme-orders/).

---

## The one problem this solves: version alignment

A zib package is a **reference, not the dependency**. The package is pinned by zib to an
immutable commit plus a content hash of the exported tree — so every checkout materializes
byte-identical prose. But the **real library lives in its own registry** (pip/npm/cargo),
which zib never sees and never controls. acme-orders documents acme-sdk **3.3.0** at commit
`a1b2c3d`; the agent installs acme-sdk from PyPI, a thing zib never touches.

The whole install concern is the discipline that **welds those two facts together**: the
version the agent installs must be provably the version the pinned prose describes. If the
agent installs a version outside what the prose was written for, `API.md`, `USAGE.md`,
`PITFALLS.md`, and `examples/` all silently lie, and the agent writes non-conforming code.

Everything below serves that weld.

### Anchor vs. window — the sharpest distinction

A package documents the library *as of* **one exact version** and asserts compatibility
*across* **a window**. These are two different facts, and conflating them is the root cause
of most version-alignment bugs:

- **The documented anchor** — the exact version the prose is provably *true of*. Every
  `API.md` signature, every `PITFALLS.md` edge, every eval assertion is true *at the
  anchor*. acme-orders' anchor is **3.3.0**.
- **The install constraint window** — the compatibility range the producer *asserts the
  prose stays true across*. acme-orders' window is **`>=3.3,<4`**. Its **floor must equal
  the anchor** (you can never claim compatibility with a version older than the one you
  documented); its **ceiling is the next prose-breaking major**.

> **The rule.** Floor == anchor. Ceiling == next major the producer believes breaks the
> prose. The agent installs *within the window*; the verify step proves the install landed
> *inside it*; the anchor is the known-good.

---

## The install artifacts

Install facts live in a small, fixed set of stable-named files. Each owns exactly one
concern so an install-only change diffs in exactly one place.

### `zib.ref.toml` — the marker · **required**

Exactly two fields zib parses: `description` (one-line selection label) and `suggested_role`
(a hint zib never auto-applies). **No version field, no dependency field.** zib parses
nothing else, so any version data here is invisible — a phantom source of truth that drifts
from the generated prose. The version is a property of the pinned commit, surfaced in
`OVERVIEW.md`/`INSTALL.md`, never here. Stays byte-identical across a pure version bump.

```toml
description    = "Acme order orchestration — place, cancel, and fulfil orders over the Acme SDK"
suggested_role = "order-orchestration"
```

### `OVERVIEW.md` — the documented-version stamp · **required**

One screen. For the install concern it does exactly two things: states the **single
documented-version + pinned-commit line**, and routes setup to `INSTALL.md`. No dependency
table, no commands, no constraint here — those belong to `INSTALL.md` alone, so a bump
diffs them there. The stamp is generated, never hand-edited.

```
This package documents acme-sdk v3.x, pinned at 3.3.0 (commit a1b2c3d). See RELEASES.md.
```

…plus the read-next row: `setting it up → INSTALL.md`.

### `INSTALL.md` — the agent's install contract · **required (for a product/library)**

The complete, isolated, executable install→verify runbook. The single home for: which real
packages, at what constraint aligned to the anchor, what env/config, and a verify step.
**Five sections in fixed order** so any change localizes:

1. **Opening reminder.** "zib does not install anything; the agent runs the real installer."
2. **Dependencies table** — `Package | Constraint | Why`. Includes the runtime/language
   floor. The direct dependency's constraint floor **equals the anchor**. Transitive deps
   appear **only when the row carries an action** (see the diff-legibility rule below).
3. **Install command** — the exact, copy-pasteable command with the constraint baked in.
   **Never `latest`, never unbounded.**
4. **Required configuration table** — `Env var | Values | Notes`. Marks which vars are
   **secret**, and **defaults everything to sandbox**.
5. **Verify the install** — an **exit-code assertion** (not a comment), with a named
   remediation for the shadowing case.

acme-orders' file is already most of this. The one upgrade the discipline demands is in
section 5, below.

#### The Dependencies table

| Package | Constraint | Why |
|---|---|---|
| Python | `>= 3.10` | the SDK uses `match` and `X \| None` types — read from the SDK's `requires-python` at the anchor |
| `acme-sdk` | `>= 3.3, < 4` | the library you import as `acme`; **floor == documented anchor 3.3.0** |
| `httpx` | `>= 0.27` | transport, pulled in by acme-sdk — **don't pin separately** (PITFALLS #5) |

Every value is a *fact about the documented release*, read from the real library's packaging
metadata at the anchor commit — not a hand-estimate. The `httpx` row earns its place because
it carries an action ("don't pin"); it is not there to enumerate the transitive tree.

#### The install command

```sh
pip install "acme-sdk>=3.3,<4"
```

Generated from the same anchor as the table, so command and table can never disagree. Per
ecosystem the shape flexes, the mechanic is identical: npm `acme-sdk@">=3.3 <4"`; cargo
`acme-sdk = ">=3.3, <4"`.

#### The verify step — an assertion, not a comment

acme-orders today ships a **comment** the agent must interpret by judgment:

```sh
python -c "import acme; print(acme.__version__)"   # expect 3.3.x
```

The discipline upgrades this to a **hard exit-code assertion** that fails non-zero when the
installed version falls outside the documented window, encoding the *same* constraint as the
install command:

```sh
python -c "import sys,acme; v=acme.__version__; sys.exit(0 if v.startswith('3.3') else 1)" \
  || echo "FAIL: acme-sdk outside documented window >=3.3,<4 (got $(python -c 'import acme;print(acme.__version__)'))"
# Remediation: a 2.x version means an older acme-sdk is shadowing it — uninstall it first.
```

The agent parses an **exit code**, not free prose. This is the cheapest possible mechanical
gate against the #1 install failure (a wrong/shadowed version making `API.md` silently lie),
and it catches that failure *before any conforming code is written*. It needs no zib feature
and no new file.

**State the verify command's runtime assumptions.** The verify must be runnable as written
in the agent's environment, or name what it assumes (here: `python` on PATH, the project's
venv active). A copy-paste gate that silently no-ops on `python3`/Windows/venv is worse than
none. Where the assumption is non-trivial, state it inline above the command.

### `RELEASES.md` — the install delta's intent layer · **required**

zib surfaces a tree diff on update, but a diff shows `>=3.2` became `>=3.3` without saying
*why* or *what to do*. `RELEASES.md` is where install-affecting changes get their intent.
One `## vX.Y.Z` heading per release, newest first, matching the documented version.

> **The rule.** Any release that moves the install constraint, the runtime floor, a
> transitive range, an env var, or a required argument **must note it here.** A skipped-
> version jump (3.1 → 3.5) then surfaces the **union** of every floor move and new
> requirement in one read.

acme-orders already does this for behavior — `v3.0.0: Dropped Python 3.9 support (now
>= 3.10)` (a runtime-floor change); `v3.3.0: idempotency_key now REQUIRED`. The discipline
makes it explicit for install-affecting changes specifically. Append-only; **never rewrite
past headings** (that corrupts the intent the agent diffs against).

**Foreground impact with a line marker.** Within a release, prefix the changes that can hurt a
consumer with a fixed token — both human- and machine-legible — and list them first (the
Conventional-Commits / Common Changelog lesson):

- **`BREAKING:`** — existing code that worked will now fail: a removed/renamed symbol, a new
  required argument, a raised runtime floor, or a changed exception a caller catches.
- **`BEHAVIORAL:`** — the signature is unchanged but the **runtime behavior** is different. This
  is precisely the case zib's mechanical diff *cannot* infer from a content change, so it **must**
  be written down — it is the producer's only channel for a behavior-only break.
- unmarked — additive or a pure fix; safe.

zib **surfaces** these markers (they ride along in the `RELEASES.md` diff) but never **parses**
them — the agent reads them to decide what to verify against existing code. zib's own routing
stays on the mechanical churn verdict (it also cross-checks the *declared* SemVer bump against
that churn: a sub-major bump whose content was rewritten is flagged as a likely SemVer violation,
"read fresh").

Two release flavors deserve an explicit tag in the heading:

- **Install-only / security.** A CVE forces the floor to `>=3.3.1` with *no documented-
  behavior change*. This is a legitimate package release purely to move the constraint; tag
  it so the agent knows **no code change is implied** — only re-install + re-verify.
- **Redesign.** A wholesale install rewrite (transport swap, package rename, new required
  service) should signal *read `INSTALL.md` fresh, do not treat as an incremental delta* —
  mirroring zib's redesign-vs-delta routing for content.

### `SOURCE.md` — the version=commit binding · **optional, high value**

Binds the documented registry version to the exact upstream commit, so the generated install
prose is provably derived from one code state. acme-orders states **`3.3.0 = a1b2c3d`** and
pins every pointer `@ a1b2c3d`. Include the **packaging-manifest pointer**
(`pyproject.toml`/`setup.cfg` @ commit) so a skeptical agent can verify the generated
Dependencies table against authoritative source. Carries the `GENERATED … regenerate on
release` note and the `if a path 404s at the pinned commit, this file has drifted` self-check.

### `API.md` — the generated-from header · **optional, high value**

Pins the public-surface prose to the anchor: `GENERATED from acme-sdk 3.3.0`. The version in
this header **must equal** the `INSTALL.md` anchor and the `SOURCE.md` commit's version; a
mismatch signals a partial regeneration — a broken package.

### `evals/smoke.py` + `evals/README.md` — the behavior gate · **high value (expected for a library)**

Distinct from `INSTALL.md`'s verify (see *two gates* below). Dependency-light (documented
library + stdlib only), runs against a **sandbox** key, prints per-line `PASS`/`FAIL` and a
final `ALL PASS`, exits 0/1. The discipline adds one thing: **re-assert the version window
first**, then exercise version-specific behavior (acme-orders tests re-cancel is a no-op
"since 3.2" and `place()` with `idempotency_key` "required since 3.3" — behavior that only
holds inside the window). `evals/README.md` states the loop, that the code is untrusted and
sandbox-only, that **zib never runs these**, and that **a green eval is evidence for the
agent's `zib confirm`, not an automatic confirm**.

### `examples/` — runnable smoke that doubles as docs · **optional, high value**

Small numbered scripts, each with a docstring giving the exact run command, expected output,
exit code, and the meaning of likely failures (acme-orders: `AcmeDeclined ⇒ your sandbox key
isn't provisioned for SHOE-1`). Sandbox-keyed. Fixtures shipped as **small text**
(`_webhook_sample.json`), **never binaries**.

---

## The version-alignment mechanism

Three reproducibility anchors must point at one release. The install concern keeps them
welded:

| Anchor | Pins | Owner |
|---|---|---|
| **zib's pin** | the package *prose tree* — `Pin(commit, content_hash)`, fetched by the immutable `resolved_commit`, never re-resolving a label | zib |
| **The source anchor** | the documented version = the upstream commit (`3.3.0 = a1b2c3d`); `API`/`INSTALL`/`SOURCE` all generated from it | the producer's generator |
| **The registry anchor** | the real install — `INSTALL.md`'s constraint window, floor == anchor | the agent's package manager |

Because **every version-coupled string is generated from one `ANCHOR_VERSION` +
`ANCHOR_COMMIT`**, the three can never disagree. The verify step turns "I installed
something" into "I installed a version provably inside the window the prose is true of."

> **No shipped file is the authority; the generator is.** `OVERVIEW.md` carries the
> orientation stamp, `INSTALL.md` carries the operational constraint + verify, `SOURCE.md`
> carries the version=commit binding — all *derived*. No shipped file is hand-edited for
> version facts, so partial drift (`API.md` says 3.5 while `INSTALL.md` says 3.3) is
> structurally impossible.
>
> **No machine-readable lock file is added.** A shipped `install.lock`/version block would
> (a) violate zib's "deterministic and dumb, parses exactly two fields" invariant and (b)
> duplicate the consumer's *real* package-manager lockfile, which zib must never compete
> with. The single source of truth is the **generator**, not a shipped artifact; the
> machine-readable contract the agent needs is the **verify command's exit code**.

### Alignment flexes by RefKind

How tightly the install pins tracks how tightly **zib itself** pinned the reference
(`RefSpec.kind`):

| RefKind | Constraint | Verify asserts | Update |
|---|---|---|---|
| **SEMVER / TAG** (the common case) | **window** `>=3.3,<4` | the **prefix/band** (`3.3.x`) — patch-freedom keeps installs resolvable and is correct because patches don't change the documented surface | shows the constraint move |
| **REV** (frozen commit) | **exact** `==3.3.0` (or the VCS commit) | the **exact** version | a no-op (frozen) |
| **BRANCH** (moving tip) | a **VCS install at the pinned commit** (`pip install "git+…@<commit>"`) or a `>=X.Y.dev` floor | a **min dev/commit-derived** version; `INSTALL.md` flags *"pinned to branch HEAD, no upper bound — the surface may have moved; re-verify every update"* | weaker by nature |

The default headline rule is **window + prefix-band verify** for the common tag case.
Exact-patch assertion is *rejected as the default* — it conflicts with the deliberate patch-
freedom that keeps installs resolvable, and breaks when an anchor is yanked (see failure
modes).

---

## The install → verify → confirm loop the agent follows

```
select → orient → materialize (zib) → install (agent) → verify version → apply
       → verify behavior → confirm
```

1. **Select.** Agent reads `zib.ref.toml` `description` + the zib inventory; picks
   acme-orders for the order-orchestration role.
2. **Orient.** Reads `OVERVIEW.md` (one screen); learns the documented anchor — *acme-sdk
   3.3.0, commit `a1b2c3d`*. Does **not** read `INSTALL.md` unless the task is install.
3. **Materialize (zib, not the agent).** `zib install` fetches the package *prose tree* by
   the immutable `resolved_commit`, verifies the content hash; idempotent (a clean install
   rewrites nothing). This makes `INSTALL.md`/`evals/` present and byte-verified. It installs
   no library and **executes nothing**.
4. **Confirm the choice with the user.** Running the real installer is a **side-effecting
   act** — it mutates the environment, PATH, and the project lockfile, unlike zib's reversible
   pin. Per the intent, the agent confirms its choice before installing.
5. **Install (agent runs the real installer).** Reads `INSTALL.md`; checks the runtime floor
   first (`python >= 3.10`) so an unmet floor fails fast, not mid-install; runs the exact
   `pip install "acme-sdk>=3.3,<4"`, pinning only the direct dep and letting the SDK carry
   transitives.
6. **Configure.** Sets `ACME_API_KEY` (sandbox) and leaves `ACME_ENV` at its sandbox default.
7. **Verify version alignment (gate 1).** Runs `INSTALL.md`'s exit-code verify. Outside the
   window → **hard stop**; the agent resolves the mismatch before writing any code, because
   the rest of the package is only valid inside the window.
8. **Apply.** Writes conforming code from `USAGE.md` + `API.md` + `examples/`, trusting the
   surface because the install is proven inside the documented window.
9. **Verify behavior (gate 2).** Runs `evals/smoke.py` against the sandbox key; it re-asserts
   the window, then exercises version-specific behavior.
10. **Confirm.** All `PASS` → agent runs `zib confirm acme-orders`, recording
    `confirmed_through` (its own assertion; the green eval is evidence, not an auto-confirm).

### Two gates, two locations, no new file

There are two distinct proofs, and conflating them makes a missing-artifact problem look
like a behavior bug:

- **Gate 1 — `INSTALL.md`'s verify.** Presence + version alignment. Code-free, no business
  logic, **offline** (import + version assertion, no network). Run first.
- **Gate 2 — `evals/smoke.py`.** Behavior + integration. Needs the sandbox service. Run
  after apply; gates `zib confirm`.

A green gate 1 localizes any gate-2 failure to integration logic, not a missing or misaligned
artifact. This realizes the conceptual split **without** mandating a new `preflight.py` file
— that would over-build for v1 and add a filename to the stable-name contract the exemplar
doesn't carry. Two gates, the existing two locations.

---

## Generated from source — the release-time build step

Install metadata is the **most version-coupled prose in the package**, so
`examples/README.md`'s principle 2 ("generated from source, never hand-asserted") applies
hardest here. At release time, before `git tag`, the producer runs a generator keyed on a
single `ANCHOR_VERSION` + `ANCHOR_COMMIT` (e.g. `3.3.0` / `a1b2c3d`) that:

- checks out the upstream commit;
- reads the real library's packaging metadata at that commit (`requires-python`,
  `install_requires`/`dependencies`, the real transitive ranges, the actual `__version__`);
- **emits** `INSTALL.md`'s Dependencies table, install command, and verify band; `API.md`'s
  signatures + header; `SOURCE.md`'s pointers; and `OVERVIEW.md`'s version stamp.

The producer **hand-authors only intent** — the new `## vX.Y.Z` heading in `RELEASES.md`.

> **The generator's output is the pinned prose; the generator itself is not shipped.** It is
> a build tool, not reference prose, and shipping it would add a non-prose file zib must
> diff. It stays out-of-band in the producer's release pipeline. The binding's auditability
> comes from `SOURCE.md`'s version=commit pointer into the packaging manifest — not from
> shipping the script.

---

## Diff legibility — one concern per file, stable names

zib's whole value is the precise delta. The install concern obeys it strictly:

- **`INSTALL.md` is the only file carrying the install constraint.** A constraint/verify/env
  change diffs `INSTALL.md` **only**. The version stamp diffs `OVERVIEW.md` only.
  `RELEASES.md` supplies the intent. A clean library bump (3.3.0 → 3.5.0) touches exactly
  `INSTALL.md` + `OVERVIEW.md` + `RELEASES.md` and nothing else.
- **Filenames and section order are a contract.** Never rename `INSTALL.md` → `SETUP.md`
  (reads as delete+add, destroying alignment). Keep the five sections in fixed order so the
  delta lines up section-by-section.
- **List a transitive only when the row carries an action.** The `httpx` row exists to say
  *don't pin this* — actionable, prevents a resolver conflict. Do **not** enumerate the full
  transitive tree; it rots and floods the diff. The test: does the row tell the agent to **do
  or not-do** something? If not, omit it. (The range itself is still generated; only
  actionable rows ship.)

---

## What lives in the consumer's `notes.md`, not the package

The package's `INSTALL.md` carries **generic instructions for the documented version**. The
**actual installed version, registry mirror choice, air-gapped/offline install steps, and
any project-specific install deviation** belong in the **consumer's `notes.md`**, never in
the package — that would violate "describes, never restates" and couple the package to one
consumer's infra.

The boundary, stated plainly:

- **zib pins the prose tree**, not the installed library.
- **The actually-installed version is recorded by the consumer's real package-manager
  lockfile** (pip/npm/cargo) and optionally `notes.md`. It is **not** a field in the package
  and **not** in zib's lockfile (which pins prose only). Version alignment is *asserted at
  verify time*, not persisted by zib.

---

## Swap teardown — reversing a prior install

The intent resets notes on swap because a different reference needs different setup — and the
install is reference-specific too. When the agent swaps acme-orders for a competing SDK, the
**old real dependency must be reversed**: uninstall the old package, unset its env vars, then
install the new one. zib's pin is reversible (a swapped-out reference stays recoverable); the
agent's install is not — so the agent owns teardown, reading the *old* package's `INSTALL.md`
to know exactly what to remove (its install command's package, its config-table env vars)
before applying the new package's `INSTALL.md`. The package's `INSTALL.md` is the manifest of
*what was added*, which is what makes a clean reversal possible.

---

## Cross-reference install posture

A project installs **multiple** zib references, and two may demand conflicting real-
dependency constraints. The intent defers cross-reference conflict rules to a later version
when real pain appears — so the install concern's stated posture is deliberately minimal:
**each package's `INSTALL.md` is independent; resolver conflicts across references are the
agent's / project's problem, not the package's.** A package never reaches across to another
reference's constraints; it pins only its own direct dependency and lets the project's real
package manager resolve the union.

---

## Failure modes — pitfall → structural prevention

| Pitfall | Structural prevention |
|---|---|
| Install `latest` / unbounded → agent gets acme-sdk 4.x while the prose was written for 3.3.0; the prose now lies. | The install command always carries a bounded window `>=3.3,<4` (ceiling = next prose-breaking major); the verify step asserts the install is inside it and fails otherwise. |
| Version shadowing — an older acme-sdk wins the import, agent integrates against a stale surface. | The verify **asserts** `__version__` is in the window (exit-code, not a comment) with a named remediation ("a 2.x means an older SDK is shadowing — uninstall it"); the eval re-asserts before exercising behavior. |
| Verify is a comment, not a check → agent installs a wrong version, sees no failure, proceeds. | The verify is a real command that exits non-zero outside the window; comments are upgraded to checks. |
| Producer bumps the anchor but only re-types it in `API.md`'s header; `INSTALL`, the eval, and `SOURCE` still say 3.3.0. | All version-coupled prose is **generated** from one `ANCHOR_VERSION`/`ANCHOR_COMMIT`; the version is authored in exactly one place, so partial drift is structurally impossible. |
| Transitive deps hand-guessed → wrong when the SDK changes its own requirement → resolver conflict. | Transitive ranges are read from the real library's metadata at the anchor commit; PITFALLS #5 reinforces deferring to the SDK ("don't pin httpx"). |
| `API.md` generated at `a1b2c3d` but `INSTALL.md` points at a different version → surface ≠ artifact. | `SOURCE.md`'s `3.3.0 = a1b2c3d` binding + generated-from headers force one `(version, commit)` pair across `API`/`INSTALL`/`SOURCE`. |
| A version field added to `zib.ref.toml` as a "convenience" → a second source of truth zib ignores and that drifts. | zib parses exactly `description` + `suggested_role`; the version lives only in generated prose. The marker stays version-free on purpose. |
| A skipped-version jump silently moves the runtime floor or adds a required env var; the agent only read the new `INSTALL.md`. | `RELEASES.md` carries every install-affecting change per version, so a multi-version jump surfaces the **union** of floor moves and new requirements. |
| Sandbox key used in production env (or vice-versa) → confusing `AcmeDeclined`. | Sandbox is the default everywhere (config table, eval, examples); production is an explicit opt-in; PITFALLS #6 names the exact symptom. |
| Missing required env var → opaque crash deep in application code. | The config table is the single declared list of what must be set; the agent sets it before verify; gate-1 verify runs offline before any integration. |
| Unmet runtime floor → `SyntaxError` on `match`/`X|None` mid-run. | A dedicated runtime-floor row with a one-line check the agent runs **first**; the floor is generated from the SDK's `requires-python`; `RELEASES.md` records every floor bump. |
| Shipping the wheel/binary so "install" diffs as "binary changed". | Ship/point-to discipline: `INSTALL.md` only **points** (constraint + command); the artifact stays in its registry. Binaries defeat zib's text diff. |
| Agent thinks `zib install` installed the real library, then writes code against an absent dependency. | `INSTALL.md` opens with "zib installs nothing"; the loop separates `zib install` (materialize prose) from the agent running the real package manager. |
| A bump buries the constraint change in unrelated edits. | One concern per file, stable names, fixed section order: a constraint/floor change diffs `INSTALL.md` only and line-aligns; `RELEASES.md` carries the matching intent. |
| Renaming `INSTALL.md` between releases breaks diff alignment. | Filenames are a cross-version contract; `INSTALL.md`/`RELEASES.md`/`SOURCE.md`/`OVERVIEW.md` keep stable names forever. |
| The anchor is yanked from the registry (3.3.0 pulled, only 3.3.1 remains) → an exact-version assertion fails on a correct install. | The default verify asserts the **window/prefix** (`3.3.x`), which tolerates a yanked patch; exact-version assertions are reserved for **REV/frozen** references. |
| Verify copy-paste silently no-ops in a Windows/venv/`python3` environment. | The verify must be runnable as written or state its runtime assumptions inline; the convention requires naming the assumption when non-trivial. |

---

## Flex by reference type

Same convention, sized to the thing. Which install artifacts appear or collapse:

### (a) Product / library — pip/npm/cargo + import (acme-orders)

**Full install anatomy.** `INSTALL.md` with all five sections (window constraint, runtime
floor, config, exit-code verify); `OVERVIEW.md` version stamp; `SOURCE.md` version=commit
binding pointing at the packaging manifest; generated `API.md` header; version-asserting
`evals/`; `examples/` as smoke. Alignment between the package tag and the real library
version is fully load-bearing. This is the maximal, canonical shape.

### (b) CLI tool / binary distributed via a manager

`INSTALL.md` keeps the manager command (`brew`/`cargo install`/`npm i -g`, or a pinned
`go install tool@v1.2.3`) and a verify that asserts the binary version, not a library import:
`tool --version  # assert band` plus `command -v tool`. Config usually collapses (sometimes a
shell-rc/PATH note — state that it **mutates** global PATH). The import-shadowing remediation
becomes a **PATH-shadowing** remediation ("an older tool earlier on PATH wins — check
`command -v`"). `evals/` shell out to the binary. The binary itself is **never shipped** —
`INSTALL.md` points at the registry.

### (c) Hosted service / HTTP API — no install

The install **command collapses** (nothing to install) unless an optional client SDK is
offered, in which case `INSTALL.md` presents an **SDK-or-raw choice** (a Dependencies row for
the optional SDK + a "or call the raw REST API at base URL X" note). The **Required
configuration table expands** to the dominant section: base URL, **API version header** (the
alignment anchor for a versioned API), credentials, region, sandbox vs. production. Verify
becomes a **connectivity + API-version check** (`curl … /version  # assert apiVersion
2024-10-01`, or an SDK call echoing the negotiated version). The documented version *is* the
API version; the API-version field lives in the config table so its diff is co-located with
credentials.

### (d) Pure spec / convention — nothing to install

`INSTALL.md`, `SOURCE.md`, `API.md`, and `examples/` **vanish** (the anatomy already says a
spec collapses to `zib.ref.toml` + `OVERVIEW.md` + the spec content + `RELEASES.md`). There
is no registry artifact, so there is **no registry anchor** to align. The only version anchor
is zib's content hash of the spec tree + `RELEASES.md` per-version intent. The "install"
concern reduces to *materialize-and-confirm*: zib materializes the spec text; "verify" is
conformance review against the spec (or, if the spec ships a validator schema, that schema is
reference **content** — pinned, diffable text — not an installed dependency), owned by the
agent. `OVERVIEW.md` carries which spec version this documents.

### Polyglot / multi-ecosystem (one reference, py + js clients)

`INSTALL.md` carries **per-ecosystem sections** (Dependencies/Install/Verify), each with its
own anchor + verify command, as part of the stable-section contract. `RELEASES.md` notes when
the ecosystems' versions **diverge**. The generator reads each package's metadata at the
anchor commit. The single-source rule still holds per ecosystem.

---

## The quality bar — ideal vs. inadequate (installation concern)

- ✅ The documented **anchor** and the install **window** are both stated, with **floor ==
  anchor** and a bounded **ceiling**
- ✅ The verify step is an **exit-code assertion** of the version window — never a `# expect`
  comment
- ✅ Every version-coupled value (constraint, transitive ranges, runtime floor, verify band,
  `API.md` header) is **generated from the real library's metadata at the anchor commit**
- ✅ Install facts live in `INSTALL.md` **only**; the version stamp in `OVERVIEW.md` only;
  intent in `RELEASES.md` only — a bump produces a **clean, single-concern diff**
- ✅ `RELEASES.md` flags **every install-affecting change** (floor, constraint, env var,
  required arg) so a skipped-version jump shows the **union** of moves
- ✅ Two gates: an **offline** presence+version check (`INSTALL.md` verify) before apply, a
  **sandboxed** behavior check (`evals/`) before `zib confirm`
- ✅ **Sandbox by default** everywhere; secrets named as secret and **never** shipped as
  values; the confusing symptom of a key mismatch is named
- ✅ Alignment tightness tracks **RefKind** (window+band for tag/semver; exact for rev; VCS
  install for branch)
- ✅ The package **points to** the registry artifact — **never ships the binary**
- ❌ `latest`/unbounded install · ❌ a `# expect` comment posing as verification ·
  ❌ hand-typed version strings · ❌ a version field in `zib.ref.toml` · ❌ a shipped
  `install.lock`/version block competing with the real lockfile · ❌ enumerating the full
  transitive tree · ❌ install prose scattered across `OVERVIEW`/`USAGE` · ❌ project-specific
  install state pushed into the package instead of `notes.md` · ❌ a renamed install file each
  release · ❌ a shipped wheel/binary
