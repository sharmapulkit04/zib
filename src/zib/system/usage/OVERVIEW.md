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

Record project-specific usage in the consumer's `notes.md` (survives updates; zib never parses it).
