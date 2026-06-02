# acme-orders — order orchestration over the Acme platform

**What it is.** A Python SDK that places, cancels, and fulfils orders against the Acme
platform. It handles idempotency, retries/backoff, and webhook reconciliation so you
don't have to.

**Use it when.** Your project needs to create or track orders on Acme.
**Not** for payments (→ `acme-pay`) or catalog/inventory (→ `acme-catalog`).

**This package documents** acme-sdk **v3.x**, pinned at **3.3.0** (commit `a1b2c3d`).
See `RELEASES.md` for per-version notes.

---

## Read next, by task

| If you're… | Read |
|---|---|
| setting it up | `INSTALL.md` |
| placing your first order | `USAGE.md` → `examples/01-place-order.py` |
| reconciling webhooks | `USAGE.md` → `examples/02-handle-webhook.py` |
| looking for a specific call | `API.md` |
| about to get bitten | `PITFALLS.md` |
| debugging / needing ground truth | `SOURCE.md` (pointers into the product repo) |
| verifying your integration works | `evals/` (run them, then `zib confirm acme-orders`) |

## The 30-second mental model

```
configure once  →  orders.place(idempotency_key=…)  →  order.id, order.status
                →  orders.get(id) / orders.cancel(id, reason=…)
webhooks         →  webhooks.verify(payload, sig)  →  Event(type, order_id)
```

Three rules that matter more than anything else (details in `PITFALLS.md`):
1. `place()` is idempotent **only** if you pass a stable `idempotency_key` (required since 3.3).
2. **Always** `webhooks.verify()` before trusting a webhook payload.
3. Treat order state as the SDK reports it — don't infer it from your own side.
