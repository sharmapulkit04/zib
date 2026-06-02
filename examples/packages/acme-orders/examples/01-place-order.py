"""Place an order — minimal, runnable, self-checking.

This is BOTH documentation and a golden example. The agent can run it against a sandbox
key to confirm the happy path works the way this package claims.

Run:
    ACME_API_KEY=sk_sandbox_... python examples/01-place-order.py
Expected:
    prints an order id, then "OK: created". Exit code 0.
    AcmeDeclined => your sandbox key isn't provisioned for SHOE-1.
"""
import os
import acme

acme.configure(api_key=os.environ["ACME_API_KEY"], env="sandbox")

order = acme.orders.place(
    items=[{"sku": "SHOE-1", "qty": 1}],
    idempotency_key="example-01-place-order",  # stable: re-running returns the same order
)

print("order id:", order.id)
assert order.status == "created", f"expected 'created', got {order.status!r}"
print("OK: created")
