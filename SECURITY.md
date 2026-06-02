# Security Policy

zib is early-stage software. We take security seriously and appreciate responsible disclosure.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private vulnerability reporting: go to the **Security** tab → **Report a
vulnerability**. This keeps the report private until a fix is available. Reports are
acknowledged as soon as possible; as a pre-1.0 project there is no formal SLA yet, but security
reports are prioritized.

## Scope note

zib is a deterministic CLI that pins and surfaces references; it **never executes** the content it
manages. The *references themselves* (examples, evals) are run by the consuming AI agent with its
own runtime — treat shipped runnable code as untrusted, like any remote dependency.

## Supported versions

zib is pre-1.0; only the latest release is supported.
