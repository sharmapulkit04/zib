"""Handle an Acme webhook — verify first, then react.

Shows the one non-negotiable rule: verify the signature before trusting the payload.
Frameworkless on purpose — `payload`/`sig` would come from your HTTP layer.

Run (with the sample fixture):
    python examples/02-handle-webhook.py
Expected:
    prints the parsed event type for the fixture; "OK". Exit code 0.
"""
import acme

# In a real handler these come from the inbound request:
#     payload = request.body                       # bytes
#     sig     = request.headers["Acme-Signature"]  # str
# Here we use a signed sample so the example is self-contained.
from pathlib import Path
sample = Path(__file__).with_name("_webhook_sample.json").read_bytes()
sig = "t=1700000000,v1=DEMOSIGNATURE"  # matches the sample under a sandbox signing key

event = acme.webhooks.verify(payload=sample, sig=sig)  # raises AcmeSignatureError if forged

handlers = {
    "order.confirmed":           lambda e: print("confirmed:", e.order_id),
    "order.partially_fulfilled": lambda e: print("partial:", e.order_id),
    "order.fulfilled":           lambda e: print("fulfilled:", e.order_id),
    "order.cancelled":           lambda e: print("cancelled:", e.order_id),
}
handler = handlers.get(event.type)
assert handler is not None, f"unhandled event type: {event.type!r}"
handler(event)
print("OK")
