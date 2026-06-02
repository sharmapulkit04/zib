# Install & setup

> zib does not install anything. This file tells the agent which real packages to install
> with the project's own package manager, and how to verify the result.

## Dependencies

| Package | Constraint | Why |
|---|---|---|
| Python | `>= 3.10` | the SDK uses `match` and `X | None` types |
| `acme-sdk` | `>= 3.3, < 4` | the library you import as `acme` |
| `httpx` | `>= 0.27` | transport, pulled in by acme-sdk (don't pin separately unless you must) |

## Install

```sh
pip install "acme-sdk>=3.3,<4"
```

## Required configuration

| Env var | Values | Notes |
|---|---|---|
| `ACME_API_KEY` | secret | Dashboard → Settings → API. Use a **sandbox** key for dev/evals. |
| `ACME_ENV` | `sandbox` \| `production` | defaults to `sandbox` |

## Verify the install

```sh
python -c "import acme; print(acme.__version__)"   # expect 3.3.x
```

If that prints a `2.x` version, an older `acme-sdk` is shadowing it — uninstall it first.
