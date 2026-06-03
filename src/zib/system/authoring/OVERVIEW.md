# Authoring a good reference

> A bundled **system reference** for *producers*: how to structure a reference so zib's diff stays
> clean and an agent can actually use it. The full convention + a worked exemplar live in the zib
> repository's `examples/` (anatomy + `acme-orders` + `INSTALLING.md`).

## The rules that matter

- **One concern per file; stable filenames across versions.** zib's whole value is the precise
  delta — a changed install step should diff one file, a new function another. Renaming files
  between versions breaks diff alignment; treat filenames as a contract.
- **Generated-from-source for anything mirroring code** (API surface, install metadata, version
  stamps). Hand-written surface docs rot; generated ones can't. Make it a release-time build step.
- **Append-only `RELEASES.md`, newest first**, with structured **`BREAKING:` / `BEHAVIORAL:`**
  markers listed first (DS5) — so a skipped-version jump surfaces the union of intervening changes,
  and behavior-only breaks (which a diff can't infer) are written down.
- **Ship prose + small runnable examples/evals; point to binaries/source, never vendor them.**
  Binaries defeat zib's text diff. The library itself is a dependency the reference *points to*.
- **Describe the reference; leave project-specific usage to the consumer's `notes.md`.**
- **Size to the slot** — readable in one agent session (tens of KB), deep enough to rarely need the
  raw repo.

## Flexes by kind

A library/SDK reference carries `INSTALL`/`API`/`SOURCE`/examples; a pure spec/convention collapses
to the marker + `OVERVIEW` + the spec content + `RELEASES`. Same convention, sized to the thing.

> See `examples/README.md` (anatomy) and `examples/INSTALLING.md` (the installation concern) in the
> zib repository for the full discipline and a complete worked example.
