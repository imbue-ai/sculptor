# Developer Documentation

Documentation for working on Sculptor itself. If you're looking for how to *use*
Sculptor, see the [user guide](../help/) instead.

All commands run from the repo root via [just](https://github.com/casey/just).
See the [justfile](../../justfile).

## Contents

- [Getting Started](getting_started.md) — prerequisites, setup, running locally
- [Database](database.md) — schema, migrations
- [Frontend details](frontend_details.md) — working with the frontend
- [Style Guide](style_guide.md) — Python and TypeScript/React conventions
  - [Backend style](style/backend.md)
  - [Frontend style](style/frontend.md)
- [Desktop App](desktop_app.md) — Electron packaging
- [Testing](testing.md) — test organization, integration tests
- [Linting](linting.md) — formatters, linters, ratchets
- [CLI Tools](cli.md) — sculpt CLI and API client
- [Tracing](tracing.md) — distributed tracing and instrumentation
- [PostHog](posthog.md) — product analytics
- [Code review rules](review/) — review categories for [Sculptor](review/sculptor.md),
  [React](review/react.md), [design](review/design.md), and [integration tests](review/integration_tests.md)

## Expectations

1. Follow the [style guide](style_guide.md)
2. Ensure all tests pass before merging
3. Fix flaky tests immediately — do not leave them on main
4. Keep documentation up to date
