# Public surface — what to call

> GENERATED from acme-sdk 3.3.0 (`acme/orders/__init__.py`, `acme/webhooks/__init__.py`).
> Do not hand-edit — regenerate on each release so this can never drift from the code.
> Only the public surface is listed; anything starting with `_` is internal.

## `acme`

- `configure(*, api_key: str, env: str = "sandbox") -> None`
  Sets process-wide credentials. Call once before any other call.

## `acme.orders`

- `place(items: list[dict], *, idempotency_key: str) -> Order`
  Create an order. Idempotent on `idempotency_key`. Raises `AcmeDeclined`.
  `items` entries: `{"sku": str, "qty": int}`.
- `get(order_id: str) -> Order`
  Fetch current state. Raises `AcmeNotFound`.
- `cancel(order_id: str, *, reason: str) -> Order`
  Cancel if `created`/`confirmed`; no-op if already `cancelled`; raises `AcmeConflict`
  if `fulfilled`.

## `acme.webhooks`

- `verify(payload: bytes, sig: str) -> Event`
  Verify signature and parse. Raises `AcmeSignatureError`. **Always call before trusting.**

## Types

- `Order`: `.id: str`, `.status: str`, `.items: list[OrderItem]`, `.created_at: datetime`
  - `status ∈ {created, confirmed, partially_fulfilled, fulfilled, cancelled}`
- `Event`: `.type: str`, `.order_id: str`, `.data: dict`
  - `type ∈ {order.confirmed, order.partially_fulfilled, order.fulfilled, order.cancelled}`

## Exceptions

`AcmeError` (base) → `AcmeDeclined`, `AcmeNotFound`, `AcmeConflict`,
`AcmeSignatureError`, `AcmeRateLimited`.

## Removed / do not use

- `orders.create(...)` — pre-3.0 name for `place()`, removed in 3.0.
- `orders._legacy_create(...)` — internal, scheduled for removal in 4.0.
