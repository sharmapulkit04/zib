# Reference Manager — Intent

> **Name:** **zib**. (Also referred to as "the tool" in places below — the intent is name-agnostic.)
>
> **What this doc is.** The north star: *what we are trying to achieve and why*, independent of how it's built. It is the durable companion to the build spec (`reference-manager-final-spec.md`) — the spec says *how*; this says *what* and *why*. **If the two ever disagree, this wins**, and the spec is brought back in line. Read this before changing anything; the mechanics exist to serve the intent below, not the other way around.

---

## 1. The intent (what I want to achieve)

I work with external **references** — specs, frameworks, conventions, and libraries I read *as reference* (an OpenSpec spec, a JSON-mapping framework, an OTLP spec). I use the same references across many projects, in a space that moves fast. Today that is painful in four specific ways, and I want each pain gone:

1. **Reuse without re-solving.** When I've figured out how to use a reference, I want to carry that to the next project — not rediscover it every time.
2. **Swap without friction.** When a better alternative fills the same need (e.g. one mapping library for another), I want to switch the *reference filling that need* cleanly, not unpick a tangle.
3. **Update and *actually know what changed*.** When I bump a reference to a new version, I want to be told *exactly what changed* and act on it — not be handed the whole thing again and trusted to spot the difference. **This is the heart of it.** Small changes buried in unchanged bulk get missed, and a missed change is a correctness failure, not an inconvenience.
4. **Customize for this project.** I want one place to record how *this* project uses a reference — and only that. I don't want to restate what the reference already says about itself.

Underneath all four is one consumer I'm really serving: **an AI coding agent.** The agent is who reads these references while working in my codebase. So "knowing what changed," "knowing how we use it here," and "reusing across projects" are all really about *making the agent reliably correct* — feeding it the right reference, at the right version, with the change foregrounded, plus my project-specific notes.

**Success, in one breath:** *I adopt a reference once and reuse it everywhere; I swap alternatives freely; when I update, I'm shown precisely what changed and can act on it; and I keep a single record of how this project uses it — all in a form an AI agent consumes reliably, and all reproducible by anyone who checks out my project.*

---

## 2. What I believe (the principles any solution must honor)

These are load-bearing. A solution that violates one of these has missed the point, no matter how clever.

- **References describe themselves; I write only the delta.** The reference's own content already says what it is. I should never be asked to restate that — I author *only* what isn't in the reference: my project-specific usage. Re-describing a reference duplicates it and drifts from it.
- **On update, foreground the change — never the whole.** The agent must be pointed *at what changed*, not handed the full reference and asked to find the difference. Full content is for first encounters; the change is for updates. This is a correctness mechanism, not an optimization.
- **The runtime consumer is an AI agent.** What the agent reads is plain prose meant for it. The tool's job is to deliver the right prose at the right moment.
- **The tool is deterministic and dumb; judgment belongs to the agent.** The tool fetches, pins, stores, surfaces, and diffs. It does not interpret references, enforce how they're used, or read my code. *Applying* a reference to code — and deciding whether the change matters — is the agent's job.
- **Include nothing the problem doesn't require.** Every concept must trace to one of the four needs above. When in doubt, leave it out and revisit only if real pain appears.

---

## 3. How we solve it (achieving the intent, without committing to tech)

Each mechanism below is described as *intent*, not implementation. The build spec turns these into concrete machinery.

### 3.1 Reuse → pin to a fixed point, and keep everything in my own version control
A reference is captured at an exact, **immutable point in time** — not "the latest," which drifts. Because it's pinned to a fixed point, anyone who checks out my project gets the *identical* reference, and I can re-create it later without surprises. Everything the tool manages lives **inside my project's own version control**, so there's no fragile external state to lose — recovering a reference is never harder than recovering a git commit. That's what makes a reference genuinely *reusable*: it travels with the project and reproduces exactly.

### 3.2 Update → surface the change, and know when "the change" is really a rewrite
This is the centerpiece. On a version bump, the tool's job is to answer **"what changed?"** and put that front-and-center:

- **The change itself is the primary signal** — a precise account of what differs between the version I had and the version I'm moving to. This is robust even when I skip versions (jump from an old version to a much newer one): the net difference still captures everything that moved, and the producer's own per-version change notes, where they exist, layer *intent* on top of the raw difference.
- **When the "change" is so large it's really a redesign, say so** — and tell the agent to read the whole reference fresh rather than treat it as an incremental delta. A delta is the right lens for an increment; it's the wrong lens for a rewrite. The tool should know the difference and route accordingly.
- **A surfaced change is about the *reference*, not my code.** It tells the agent what moved in the reference; it does *not* claim my code already conformed to the old version. The agent applies the change by default, but verifies against existing code when the change interacts with how the project already behaves.

The failure this exists to prevent: a small-but-important change slipping by unnoticed because it looked "basically the same." Foregrounding the change is how we make that failure structurally hard to hit.

### 3.3 Swap → replace the reference filling a need, as a first-class move
Each reference fills a **need** (a "slot" — e.g. "JSON mapping," "spec-driven development"). Swapping means replacing *the reference currently filling that need* with a different one, cleanly and in one step — not a fragile remove-then-re-add. My old project notes don't carry over, because they were specific to the old reference; a different reference needs different notes. Nothing is ever destroyed irrecoverably — a swapped-out reference remains recoverable.

### 3.4 Customize → one place for project-specific usage, and nothing else
I write **only** how this project uses a reference — the project-specific delta on top of the reference's own self-description. The tool stores and surfaces these notes verbatim and never parses, validates, or polices them. Notes **survive an update** (same reference, newer version — my usage still mostly applies) but **reset on a swap** (different reference — different usage). That survives-vs-resets asymmetry is deliberate: it encodes what should persist and what shouldn't, without needing a more elaborate system.

> *Honest boundary:* this leans on references being structured to describe themselves usefully. When a reference's own content isn't a usable self-description, it's legitimate for my notes to carry some orientation — that's my judgment as the consumer, not a violation of the principle.

### 3.5 The tool stays out of my code
The tool manages references, notes, and changes. It never reads or judges my codebase. Where a reference meets the code is the agent's domain — that separation is what keeps the tool deterministic and trustworthy.

### 3.6 My agent operates the tool; I just talk to my agent
I never run the tool by hand. I instruct my AI coding agent in plain language ("install our specs", "apply the auth spec", "find a better spec for this need"), and the agent uses the tool to do it. Two verbs stay separate: the tool **installs** (makes a reference's content present and pinned); the **agent applies** it (writes the conforming code) and records durable usage decisions in the notes on my behalf. The agent also does the *finding* — turning "the OpenSpec spec" or "a better fit for this need" into a concrete source — and confirms its choice with me before adding or swapping; the tool then pins it deterministically. The tool is the agent's hands; the agent is the judgment; I work entirely through the agent.

---

## 4. Scope I've chosen for v1 (intent-level boundaries)

Deliberate boundaries, so v1 stays small and honest:

- **References that live in git repositories — any host** (GitHub, GitLab, Bitbucket, self-hosted, or a local git repo), tracked by **either a release tag/version *or* a branch.** Git gives the intent everything in one well-understood place: an authoritative version list, an immutable commit to pin to, the exact change between any two commits, and the producer's notes (for a tracked branch, the commit log stands in). Other upstreams (plain URLs, package registries, unversioned local directories) are a later expansion behind a stable source boundary, added only when a real need appears — not a v1 concern.
- **One layer of notes.** The survives-on-update / resets-on-swap behavior already captures the only distinction v1 needs.
- **No "what problem does this solve" layer.** The reference describes itself; restating that would duplicate and drift.
- **One way to surface a change**, with the redesign-escape-hatch above. Not a configurable pipeline.

---

## 5. Explicitly *not* this (and why)

Named here so they read as decisions, not oversights:

- **A replacement for package managers.** This manages *non-code references*. It complements language package managers; it never competes with them.
- **Cross-reference composition / conflict rules.** Only if references actually start conflicting in practice.
- **Multiple tiers of notes, shared "need" definitions, controlled vocabularies, producer-side authoring tools, auto-installation into agent tooling.** Each is a real possible future; none earns its place until real pain shows up. v1 stays minimal on purpose.

---

## 6. The north star, in one sentence

> **Let a developer carry references across projects, swap and update them without friction, and — above all — always know exactly what changed on an update, so the AI agent reading them stays correct.**

Everything in the build spec is in service of that sentence. If a proposed feature doesn't move one of the four needs in §1 or honor a principle in §2, it doesn't belong in v1.
