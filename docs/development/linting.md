# Linting and Code Quality

## Quick Reference

```bash
just format     # Auto-fix formatting (ruff, eslint, stylelint)
just lint       # Lint Python (ruff) and JS/TS (eslint) and SCSS (stylelint)
just typecheck  # Type check Python (pyre) and JS/TS (tsc)
just ratchets   # Run the ratchets binary to enforce specific code styles
just check      # Run everything: lint, typecheck, ratchets, file hygiene
```

## Formatters and Linters

| Tool | Language | What it does |
|---|---|---|
| `ruff` | Python | Formatting + linting |
| `pyre` | Python | Type checking |
| `eslint` | JS/TS | Linting + formatting |
| `tsc` | JS/TS | Type checking |
| `stylelint` | SCSS | Style linting (including design token enforcement) |

### Python (ruff, pyre)

Common suppression comments:

- `# noqa: F811` — pytest fixture parameters that shadow imports (don't rename them)
- `# noqa: E731` — intentional lambda assignments (don't convert to functions)
- `# noqa: E402` — intentional late imports
- `# noqa: E712` — SQLAlchemy comparisons like `column == False`

### Frontend (eslint)

Config: `sculptor/frontend/eslint.config.ts`. Key rules enforced:

- **Explicit return types** on all functions and components
- **Arrow functions only** for React components (no `function` declarations)
- **Boolean naming** must use `is`, `has`, `can`, `should`, `does`, `are`, `will`, `did` prefixes
- **Handler naming** — event handler props prefixed with `on*`, implementations with `handle*`
- **No default exports** — always use named exports
- **Import sorting** via `simple-import-sort`
- **Type generics** must match pattern `^T[A-Z]?` (e.g. `TRequest`, `TFoo`)
- **`type` over `interface`** — enforced via `consistent-type-definitions`
- **`@ts-expect-error` over `@ts-ignore`** — must include a description

### Frontend (stylelint)

Config: `sculptor/frontend/.stylelintrc.json`. Extends `stylelint-config-standard-scss`.

- **Class selectors** must be camelCase
- **Properties** must be alphabetically ordered
- Three custom rules via `sculptor/frontend/scripts/stylelint-plugin-design-tokens/`:

| Rule | What it does |
|---|---|
| `sculptor/no-hardcoded-values` | Enforces design tokens instead of hardcoded pixel values, hex colors, and numeric constants |
| `sculptor/no-var-fallback` | Prevents CSS variable fallbacks in `var()` |
| `sculptor/no-uppercase-custom-property` | Enforces lowercase custom property names |

The `no-hardcoded-values` rule dynamically parses token sources (Radix UI's `base.css` and `src/styles/tokens.css`) to build value-to-token mappings and suggest replacements. Radix overrides live in `src/styles/radix-overrides.css`.

Run stylelint standalone:

```bash
npm run lint:styles    # from sculptor/frontend/
```

## Ratchets

Ratchets enforce code quality rules (regex and tree-sitter AST). They count
occurrences of banned patterns and fail if the count exceeds a per-rule budget.
They run in CI.

Enforcement is handled by the [`ratchets`](https://crates.io/crates/ratchets)
binary (install with `just install-ratchets`; included in `just rebuild`).
Configuration lives at the repo root:

- `ratchets.toml` — schema, languages, and the enabled rule set (`$sculptor`).
- `ratchets/sets/sculptor.toml` — the curated set listing every enabled rule.
- `ratchets/regex/` — sculptor-specific custom rules not shipped in the binary.
- `ratchet-counts.toml` — the per-rule violation budgets.
- `.ratchetignore` — paths excluded from measurement (gitignore format).

```bash
just ratchets           # Check all ratchets (ratchets check)
just ratchets-broken    # Show ratchet violations in files you changed (ratchets check --since origin/main)
just ratchets-update    # Re-pin budgets to current counts (ratchets bump --all)
```

If a ratchet fails, you likely added a new use of a banned pattern. Fix the
violation or, if the pattern is in a file that shouldn't be measured, add it to
`.ratchetignore`.

### Adding a Ratchet

Most rules ship inside the binary — enable one by adding its ID to
`ratchets/sets/sculptor.toml`. For a sculptor-specific rule, drop a TOML file in
`ratchets/regex/` (or `ratchets/ast/`) and add its ID to the set. Then run
`just ratchets-update` to seed its budget.

## File Hygiene

`just check` also verifies:
- All text files end with a newline
- No trailing whitespace
- YAML syntax is valid
- `uv.lock` files are up to date
- Shell scripts pass `shellcheck`
