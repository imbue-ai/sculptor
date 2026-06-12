# Testing

## Test Strategy
Always prefer TDD for any code changes.

When fixing bugs, all fixes MUST have an integration (e2e) test using Playwright. The only exception is when it is actually impossible to reproduce the bug through the UI — only then may you fall back to a unit test.

**Purely visual bugs MUST NOT have automated tests.** Verify those with before/after screenshots instead. In particular, you MUST NOT write integration tests whose only assertions read layout properties (CSS dimensions, line-clamp, clipping, `page.evaluate()` reads of computed style, etc.) — those tests assert rendering, not behaviour, and the right evidence is a screenshot. See `docs/development/review/integration_tests.md#no_layout_only_tests`.

**Bugs whose behaviour depends on real Claude (e.g. agent stdin/stdout protocol, Claude binary behaviour, subagent runtime) MUST be verified against real Claude** — `fake_claude` cannot faithfully model these. Use `/auto-qa-changes` (which runs real Claude by default) for the after-fix verification. `fake_claude` remains the correct standin when the bug is about Sculptor's own UI and does not depend on Claude's actual responses.

**"Impossible" means exactly one of these:**
- The buggy code path is not reachable from any UI surface (e.g. it is internal-only, a CLI-only entrypoint, or a background job with no UI trigger).
- The bug only manifests under conditions Playwright cannot produce (e.g. OS-level signals, real network partitions, specific hardware states).
- The bug is in code that runs before the UI is available (e.g. app startup, native installers).

**"Impossible" does NOT mean:**
- "Difficult," "slow," "flaky," "inconvenient," or "the setup is annoying."
- "I hit an error and a unit test would be easier."
- "I don't know how to write the Playwright test." (Ask, don't fall back.)

If you believe the bug qualifies for fallback, you MUST get explicit user approval via `AskUserQuestion` before writing a non-integration test — do not decide unilaterally.

## Test Framework
- **Backend unit tests:** pytest (parallel with `-n 8`)
- **Frontend unit tests:** Vitest
- **Integration tests:** pytest + Playwright (Chromium)
- **Run all unit tests:** `just test-unit`
- **Run backend unit tests:** `just test-unit-backend`
- **Run backend unit tests on Offload (Modal):** `just test-unit-offload` (cloud alternative; see "When to use Offload" below)
- **Run frontend unit tests:** `just test-unit-frontend`
- **Run integration tests:** use the `/run-integration-test` skill (do NOT run pytest directly)
- **Run a single backend test:** `uv run --project sculptor pytest path/to/test.py::test_name -v`
- **Test location:** backend unit tests next to source in `sculptor/sculptor/`, integration tests in `sculptor/tests/integration/`
- **Conventions:** test files named `*_test.py` or `test_*.py`; see `sculptor/pytest.ini` for markers and config

### When to use Offload for backend unit tests

Default to local `just test-unit-backend` (`pytest -n 8`): on an idle machine it is
~1.5× faster than Offload (≈90s vs ≈135s warm) and free. Reach for
`just test-unit-offload` (runs the suite across Modal cloud sandboxes; config in
`offload-unit.toml`) only when one of these holds:

- **The machine is under load / CPU-contended** (e.g. several agents running at once).
  Offload's wall-clock is independent of local load, so when local cores are saturated
  and `-n 8` crawls, Offload still finishes in ≈135s.
- **You're chasing local-only flakiness.** Offload runs each batch in an isolated Linux
  sandbox; load/timing-sensitive tests that flake locally (e.g. PTY/subprocess tests)
  tend to pass deterministically there, on the same Linux collection CI uses.

Caveats: the first run after a dependency change does a full Modal image build (several
minutes); warm runs are ≈2–2.5 min. Offload collects a slightly different Linux set
(~1203 vs ~1208 locally).

## Bug Tracking
- **System:** Linear
- **Ticket ID format:** `SCU-<number>` (e.g. SCU-123)
- **How to fetch ticket context:** use the `/linear` skill
- **When to fetch:** whenever input matches ticket format
- **How to file new tickets:** use the `/linear` skill's `create-ticket` entry point
- **How to comment on tickets:** use the `/linear` skill's `comment` entry point
- **How to change ticket state:** use the `/linear` skill's `set-state` entry point
- **Needs-info state name:** `Triage`

## Manual Testing
- **How to test:** use the `/auto-qa-changes` skill
- **Notes:** launches Sculptor in a headless browser with an HTTP API for interaction

## Test Debugging
- **How to debug integration tests:** use the `/debug-integration-test` skill

## Test Writing
- **How to write integration tests:** use the `/write-integration-test` skill
- **Test types and locations:**
  - Backend unit tests: next to source in `sculptor/sculptor/`
  - Frontend unit tests: next to source in `sculptor/frontend/src/`
  - Integration tests: `sculptor/tests/integration/frontend/`
  - Acceptance tests: `sculptor/tests/acceptance/`
