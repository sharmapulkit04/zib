# Source map — go deeper when the prose isn't enough

> Pointers into the product repo `github.com/acme/acme-sdk`, pinned to the commit this
> package documents: **3.3.0 = `a1b2c3d`**. Read these out-of-band with your own tools when
> you need ground truth. These bytes are **not** pinned by zib — the commit makes them
> reproducible; follow them only when the curated prose above is insufficient.
>
> GENERATED: paths verified to exist at `a1b2c3d`. Regenerate on release.

| To understand | Read | Why it's worth a look |
|---|---|---|
| valid order states & transitions | `src/acme/orders/state.py` @ `a1b2c3d` | the authoritative state machine `USAGE.md` summarizes |
| idempotency-key semantics (subtle) | `src/acme/orders/_idempotency.py` @ `a1b2c3d` | exactly when a key dedupes vs. creates anew |
| retry / backoff policy | `src/acme/transport/retry.py` @ `a1b2c3d` | what `AcmeRateLimited` means and when it surfaces |
| webhook signature scheme | `src/acme/webhooks/_sign.py` @ `a1b2c3d` | the HMAC construction `verify()` checks |

If a path here 404s at the pinned commit, this file has drifted — regenerate it from
source rather than trusting it.
