# Evals — verify the integration, then confirm

These are how the **agent self-checks** that it integrated acme-orders correctly. They turn
"I think it works" into a runnable PASS/FAIL.

## The loop

1. Apply the package to your code (per `USAGE.md` / `API.md`).
2. Run the smoke eval against a **sandbox** key:
   ```sh
   ACME_API_KEY=sk_sandbox_... python evals/smoke.py
   ```
3. **All PASS** → the integration matches what this package documents → `zib confirm acme-orders`.
   **Any FAIL** → fix, or check `PITFALLS.md` / `SOURCE.md`; do **not** confirm.

## Rules

- **zib does not run these.** zib only stores and surfaces files; the agent runs evals with
  its own runtime and judgment. (This is what keeps zib deterministic and dumb.)
- **Treat eval code as untrusted** — it shipped from a producer, like any dependency. Read
  it first; run it sandboxed.
- **Evals gate the agent's `confirm`, never zib's.** `confirmed_through` stays the agent's
  assertion; a green eval is *evidence for* that assertion, not an automatic confirm.
- Keep them **dependency-light** (only `acme-sdk` + stdlib here) so the agent can actually run them.
