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

`just source` (alias `just start-onboard`) runs the app from source the way a
fresh clone behaves for a real user — the full first-run flow: welcome,
onboarding, and repo selection. It resets local dev state each run, so every
launch is a true first-run.

```bash
just source
```

Skip onboarding with `just start` — it seeds an onboarded config and lands
straight on the new-workspace form for the current repo, preserving your dev
state:

```bash
just start
```

`just stop` tears down the session (both frontend and backend); only one runs
per checkout at a time.

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
