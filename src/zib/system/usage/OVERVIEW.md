# Using zib day to day

> A bundled **system reference**: the verbs and the loop.
> *(CLI forthcoming; the commands shown are the target surface.)*

## The verbs

| Verb | What it does |
|---|---|
| `zib add <name> --source <git> --spec <version>` | pin a new reference |
| `zib install` | materialize all declared references at their locked pins (reproduce on checkout) |
| `zib status` / `zib outdated` | what's pending — available updates + owed deltas |
| `zib diff <name>` | what changed; read it before applying |
| `zib update <name>` | re-pin to newest **within** the constraint (no `zib.toml` change) |
| `zib upgrade <name> <spec>` | **move** the constraint and re-pin (rewrites `zib.toml`; deliberate) |
| `zib confirm <name>` | record that the code now conforms through the current pin |
| `zib swap <name> …` | replace the reference filling a role (notes reset) |
| `zib remove <name>` | drop a reference |

## The loop

```
poll → update | upgrade → diff → apply to code → confirm
```

- `zib status`/`outdated` tells you whether an update is **within** the constraint (`update`) or
  **beyond** it (`upgrade`).
- `zib diff` gives you the deterministic delta + a magnitude verdict (incremental vs read-the-whole-
  thing-fresh) + the producer's `RELEASES` notes with `BREAKING:`/`BEHAVIORAL:` markers.
- **You** interpret and apply; zib computes and records. Read the change — never assume.
- After applying, `zib confirm` closes the owed-delta gap.

## Notes — your project-specific usage

Record how *this* project uses a reference in its **`notes.md`** — only the delta on top of what the
reference already says about itself (don't restate the reference).

- **Where:** `.zib/references/<name>/notes.md`. **Opt-in** — create it only when you have something
  project-specific to record (no empty stubs).
- **How:** edit the file **directly**, with the same tools you edit code. There is **no `zib note`
  command** — zib stores `notes.md` verbatim and never parses it.
- **What NOT to touch:** never edit zib's generated content (`.zib/references/<name>/<label>/…`) or
  `zib.lock` — they are verified against the pin, and zib flags hand-edits.
- **Lifecycle:** notes **survive** an update (same reference, newer version) and **reset** on a swap
  (a different reference needs different usage; the old notes archive to git, recoverable).

Read a reference's `notes.md` for project context *before* applying it.
