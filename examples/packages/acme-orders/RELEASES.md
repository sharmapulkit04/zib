# Releases

> Per-version notes. zib reads this on `update`/`diff` and layers it on top of the tree
> diff as the *intent* behind a change. One `## vX.Y.Z` heading per release, newest first,
> append-only. Changes that can hurt a consumer are prefixed **`BREAKING:`** (old code now
> fails) or **`BEHAVIORAL:`** (same signature, different runtime behavior — the kind a code
> diff can't infer) and listed first; unmarked entries are additive or pure fixes.

## v3.3.0
- **BREAKING:** `orders.place()` gains a now-REQUIRED `idempotency_key`; calls without it
  raise `TypeError`. Migrate: pass a stable key per logical order (see `PITFALLS.md` #1).
- **BEHAVIORAL:** `cancel()` now raises `AcmeConflict` (was a generic `AcmeError`) on a
  fulfilled order — same call, different exception a caller may catch.
- Added webhook event `order.partially_fulfilled` and order status `partially_fulfilled`.

## v3.2.0
- **BEHAVIORAL:** `orders.cancel()` is now a **no-op** on an already-cancelled order instead
  of raising — same signature, changed outcome.
- Transport: automatic retry with exponential backoff on `429`/`503`; surfaces
  `AcmeRateLimited` only after retries are exhausted.

## v3.1.0
- **BEHAVIORAL:** `Order.created_at` is now timezone-aware (`datetime` with `tzinfo`) — same
  field, different value semantics; a naive-datetime comparison that worked before now raises.
- Added `orders.get()`.

## v3.0.0
- **BREAKING:** `orders.create()` renamed to `orders.place()`.
- **BREAKING:** dropped Python 3.9 support (now requires `>= 3.10`).
