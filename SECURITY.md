# Security

> **Sculptor is experimental and is expected to be run locally only.** It's in
> active beta and is designed to run on your own machine — not exposed to a
> network or run as a shared or hosted service. Keep that in mind when evaluating
> its security.

## Please don't send AI-generated reports

We don't accept AI-generated security reports. We get a lot of them, and we don't
have the resources to triage automated noise. Sending one is grounds for a ban —
the same bar we hold contributions to in [`CONTRIBUTING.md`](CONTRIBUTING.md). A
good report comes from a person who understands the issue and can explain it.

## Reporting a vulnerability

Please report security issues privately — **don't open a public issue.**

Use GitHub's private vulnerability reporting: the
[**"Report a vulnerability"**](https://github.com/imbue-ai/sculptor/security/advisories/new)
button under the repository's Security tab. A good report includes:

- What the vulnerability is and its impact.
- Steps to reproduce, ideally with a minimal example.
- The Sculptor version and your OS.

We'll acknowledge your report, keep you posted as we work toward a fix, and may
follow up for more detail. We appreciate responsible disclosure and will make
every effort to credit your work.

### Escalation

If you haven't heard back within 6 business days, email **security@imbue.com**.

## Threat model

Sculptor drives coding agents that can read and write files, run commands, and
reach the tools and git remotes you've connected. **Agents act with your
access.** Each task runs in its workspace — a separate copy of your
repo — and for stronger isolation you can run agents in the experimental
[container backend](docs/help/experimental/container_backend.md) (Docker or a
remote).
