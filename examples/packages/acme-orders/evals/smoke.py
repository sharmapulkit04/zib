"""Smoke eval — the agent runs this to verify its integration, then `zib confirm`.

zib NEVER runs this. The consuming agent runs it, with its own runtime, after applying
the package to code. Treat it as untrusted remote code (it came from a producer): read it
before running, run it against a SANDBOX key only.

Exercises the main path end-to-end: place -> get -> cancel.

Run:
    ACME_API_KEY=sk_sandbox_... python evals/smoke.py
Pass:
    every line prints "PASS", final line "ALL PASS", exit code 0.
Fail:
    the failing check prints "FAIL: ...", exit code 1.
"""
import os
import sys
import acme


def check(name, cond):
    print(f"{'PASS' if cond else 'FAIL'}: {name}")
    return bool(cond)


def main() -> int:
    acme.configure(api_key=os.environ["ACME_API_KEY"], env="sandbox")
    ok = True

    order = acme.orders.place(
        items=[{"sku": "SHOE-1", "qty": 1}],
        idempotency_key="zib-eval-smoke",
    )
    ok &= check("place() returns a created order", order.status == "created")
    ok &= check("order has an id", bool(order.id))

    fetched = acme.orders.get(order.id)
    ok &= check("get() round-trips the same order", fetched.id == order.id)

    cancelled = acme.orders.cancel(order.id, reason="zib-eval")
    ok &= check("cancel() moves it to cancelled", cancelled.status == "cancelled")

    # Idempotency: re-cancel is a no-op, not an error (since 3.2).
    again = acme.orders.cancel(order.id, reason="zib-eval")
    ok &= check("re-cancel is a no-op", again.status == "cancelled")

    print("ALL PASS" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
