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

**The local app is a trust boundary.** Sculptor runs a local web server (HTTP
and WebSockets) bound to `127.0.0.1`. A per-session token stops web pages you
visit in a browser from reaching it. But the loopback interface itself is the
boundary: any process on the same machine that can open a connection to that
port can reach the API. Don't run Sculptor on a machine you share with people
you don't trust, and don't expose its port to a network (port-forwarding, or
binding the experimental container backend to a non-loopback address).

**Opening a repository runs its code.** Setting up a workspace runs the
project's setup command and honors repo-provided environment (e.g. a checked-in
`.sculptor/.env`), so opening a project can execute code on your host before any
agent starts. Only open repositories you trust — treat "open this repo" like
"run this repo."

**Adding a plugin runs its code.** Frontend plugins load from a source you add
— a local path or a remote or local URL — and run inside the app with the same
privileges as Sculptor's own UI: they share the host's renderer and can reach
everything it can, including the loopback API and the tools and remotes you've
connected. A remote source is fetched on every load, so you're trusting whatever
it serves at that moment, not just the code you saw when you added it. Only add
plugin sources you trust — treat "add a plugin" like "run this code" — and
prefer pinned, local sources over URLs that can change under you.
