# Getting Started

## Prerequisites

- [Homebrew](https://brew.sh/)
- [tmux](https://github.com/tmux/tmux): `brew install tmux`
- [just](https://github.com/casey/just): `brew install just`
- [uv](https://github.com/astral-sh/uv): `brew install uv`
- [nvm](https://github.com/nvm-sh/nvm)

## Building

From the repo root:

```bash
just clean rebuild
```

## Running Locally

Start the frontend and backend in a tmux session:

```bash
just start
```

`just start` is the fast-QA path: it seeds an onboarded dev config so the app
skips the welcome flow and lands straight on the new-workspace form for the
current repo, ready to create a workspace. It's idempotent — safe to re-run.

To instead run the app the way a fresh clone behaves for a real user — the full
first-run flow, welcome through onboarding and repo selection, from source — wipe
the dev state and launch with no initial project:

```bash
just source   # alias: just start-onboard
```

Either way, `just stop` tears down the whole session (both frontend and
backend); only one can run per checkout at a time.

Or run them separately:

```bash
just backend   # in one terminal
just frontend  # in another
```

After pulling new changes, rebuild:

```bash
just rebuild
```

To clear your database and other local state files:

```bash
# when running with just start
mv <repo>/.dev_sculptor <repo>/.dev_sculptor.bkp
```

## Running Tests

```bash
just test-unit
just test-integration
```

## Code Quality

```bash
just format     # Auto-fix formatting (ruff, eslint)
just lint       # Lint Python and JS/TS
just typecheck  # Type check Python (pyrefly) and JS/TS (tsc)
just ratchets   # Run ratchet checks (needs `just install-ratchets`)
just check      # Run all checks, see <repo>/justfile
```

See the [style guide](style_guide.md) and [testing docs](testing.md) for details.
