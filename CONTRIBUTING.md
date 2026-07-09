# Contributing to Sculptor

Our team is small, and we don't have a ton of bandwidth to properly support and
review every contribution. We genuinely want to — but rushing into it would
overwhelm us and create a bad experience for everyone. We'd rather do this right
than do it fast.

So for now we keep contributions on a short leash. The approach is inspired by
[pi](https://github.com/earendil-works/pi)'s
[contribution model](https://github.com/earendil-works/pi/blob/main/CONTRIBUTING.md) —
credit to them for figuring out something that works for a small team — though
we've loosened it: **issues are open to everyone; only pull requests are gated.**

## Start with an issue

**Issues are open to everyone — file away.** Found a bug, want to propose a
change, curious about direction? Open an issue. That's how you reach us.

**Opening a pull request is gated.** We only accept PRs from contributors we've
cleared. Here's how you get cleared: open an issue, and if we want the change and
you'd like to build it, a maintainer replies **`lgtm`** — that clears you to open
PRs from then on. PRs from anyone who hasn't been cleared are closed
automatically with a note. We go through all closed PRs.

If it's something we want and you've said you'd like to build it, a maintainer
may reply `lgtm` to clear you for a PR.

## Opening a PR

Once you've got an `lgtm`, here's what helps it land:

- **Keep it small.** Focused bug fixes, reliability tweaks, and minor
  performance improvements are easiest for us to accept.
- **Explain the what and the why.** Tell us what changed and why it belongs in
  the project.
- **Don't mix unrelated changes.** One PR, one purpose.
- **Show, don't tell.** Include before/after images for UI changes, and a short
  video if motion or interaction is involved.
- **Run the checks first.** From the repo root, `just format`, `just check`, and
  `just test-unit` should all pass. (New here?
  [`docs/development/getting_started.md`](docs/development/getting_started.md)
  gets you set up; `just rebuild` installs dependencies.)

## What we're unlikely to accept

A few things, up front, so you don't waste your time: large PRs, drive-by
features, opinionated rewrites, or anything that expands scope.

## Be realistic about what a PR means

Opening a PR doesn't create an obligation on our side. We have full discretion
over what gets merged — which means we may close your PR, defer it, ask you to
shrink it, or build the idea ourselves later.

If you're fine with that, go for it.

## Spam and blocking

We'll block accounts that abuse the tracker. If you ignore this document twice,
or fire a volume of agent-generated issues or PRs at the repo, we'll block you.

## Security

Please don't file security issues in the public tracker. See
[`SECURITY.md`](SECURITY.md) for how to report a vulnerability privately.

## Questions

Open an issue or use the discussion.

---

If you've read this far and you're still excited to give it a whirl, we look
forward to seeing what you build.
