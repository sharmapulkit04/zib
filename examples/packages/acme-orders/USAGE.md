# Usage — the core tasks, most common first

Configure once per process, then call the `orders` and `webhooks` namespaces.

```python
import os, acme
acme.configure(api_key=os.environ["ACME_API_KEY"], env=os.getenv("ACME_ENV", "sandbox"))
```

## 1. Place an order

```python
order = acme.orders.place(
    items=[{"sku": "SHOE-1", "qty": 1}],
    idempotency_key="checkout-7f3a",   # REQUIRED since 3.3; make it stable per logical order
)
order.id        # "ord_..."
order.status    # "created"
```

Retrying `place()` with the **same** `idempotency_key` returns the same order instead of
creating a second one. This is your safety net against double-submits — use it.

## 2. Look up / cancel

```python
acme.orders.get(order.id).status            # current status
acme.orders.cancel(order.id, reason="customer_request")
```

`cancel()` is valid while status is `created` or `confirmed`; it is a **no-op** (not an
error) if the order is already cancelled. It raises `AcmeConflict` once the order is
`fulfilled` — fulfilled orders can't be cancelled, only returned (out of scope here).

## 3. Reconcile webhooks

Acme calls your endpoint as orders progress. Verify, then switch on `event.type`:

```python
event = acme.webhooks.verify(payload=request.body, sig=request.headers["Acme-Signature"])
match event.type:
    case "order.confirmed":          ...
    case "order.partially_fulfilled":...   # added in 3.3
    case "order.fulfilled":          ...
    case "order.cancelled":          ...
```

`verify()` raises `AcmeSignatureError` on a bad/forged signature — never trust an
unverified payload. See `examples/02-handle-webhook.py` for a complete handler.

## Errors you'll handle

| Exception | When | Typical response |
|---|---|---|
| `AcmeDeclined` | order rejected (e.g. SKU unavailable) | surface to user; don't retry blindly |
| `AcmeNotFound` | unknown `order_id` | 404 your side |
| `AcmeConflict` | illegal transition (e.g. cancel a fulfilled order) | reject the action |
| `AcmeSignatureError` | webhook signature invalid | drop the request, alert |
| `AcmeRateLimited` | too many calls | the SDK already retries with backoff; only seen after retries exhaust |
