# Pitfalls — the sharp edges

Ordered by how often they bite.

1. **Forgetting `idempotency_key`, or making it random.**
   Since 3.3 it's required, but a *random* key per attempt defeats the point — a retried
   request creates a duplicate order. Derive it from something stable (cart id, checkout id).

2. **Trusting an unverified webhook.**
   Parsing `request.body` as JSON without `webhooks.verify()` accepts forged events. Always
   verify first; a bad signature raises `AcmeSignatureError`.

3. **Inferring order state locally.**
   Don't assume an order is `confirmed` because `place()` returned. Confirmation is async and
   arrives via `order.confirmed`. Read `order.status` / react to webhooks; never shadow it.

4. **Cancelling a fulfilled order.**
   `cancel()` no-ops on already-`cancelled` but **raises `AcmeConflict`** on `fulfilled`.
   Check status (or catch the conflict) before offering a cancel action.

5. **Pinning `httpx` against the SDK.**
   `acme-sdk` tracks a compatible `httpx` range; an over-tight pin on your side causes
   resolver conflicts. Let the SDK carry it unless you have a hard reason.

6. **Mixing sandbox and production keys.**
   A sandbox key in `production` env (or vice-versa) fails as `AcmeDeclined` with a confusing
   message. Set `ACME_ENV` to match the key.
