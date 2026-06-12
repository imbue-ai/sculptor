# stylelint-plugin-design-tokens

A custom stylelint plugin that enforces the use of design tokens instead of
hardcoded values in SCSS files. This ensures visual consistency across the
Sculptor frontend by catching raw pixel values, hex colors, and numeric
constants that should reference token variables.

## Rule: `sculptor/no-hardcoded-values`

The plugin provides a single rule that flags hardcoded values and suggests the
appropriate design token replacement.

### What it checks

| Property | Flagged values | Expected replacement |
|---|---|---|
| `font-size` | `Npx` (e.g. `14px`) | `var(--font-size-*)` |
| `font-weight` | `300`, `400`, `500`, `600`, `700` | `var(--font-weight-*)` |
| `border-radius` | `Npx` (e.g. `6px`) | `var(--radius-*)` |
| `z-index` | Any value >= 10 | `var(--z-*)` |
| `transition` / `transition-duration` | Duration values (e.g. `200ms`, `0.3s`) | `var(--duration-*)` |
| Spacing props (`margin`, `padding`, `gap`, `top`, etc.) | Known spacing px values | `var(--space-*)` |
| Any property | Hex colors (e.g. `#ff6b6b`, `#fff`) | Radix color variable or semantic token |

### What it ignores

- Values already using `var()` or `calc()` are always accepted
- Relative units like `em`, `%`, `vh` are not flagged
- Properties not in the checked set (e.g. `width`, `height`) are not flagged
  for pixel values
- `z-index` values below 10 are allowed (for simple stacking like `z-index: 1`)

## How it works

### Architecture

```
index.js          - Plugin entry point, registers the rule with stylelint
rule.js           - Rule implementation, walks CSS declarations and reports violations
token-parser.js   - Parses token source files to build value-to-token mappings
```

### Token resolution

The plugin dynamically builds a mapping of raw values to token variable names
by parsing two source files at lint time:

1. **Radix UI base.css** (`node_modules/@radix-ui/themes/tokens/base.css`) -
   Provides spacing (`--space-*`), font size (`--font-size-*`), border radius
   (`--radius-*`), and font weight (`--font-weight-*`) tokens.

2. **Custom tokens.css** (`src/styles/tokens.css`) - Provides duration
   (`--duration-*`), z-index (`--z-*`), and supplementary font tokens defined
   by the project.

Token mappings are cached per stylelint run so the files are only parsed once.

When a violation is found, the error message includes a suggestion with the
matching token name (e.g. `Use var(--space-4) instead`). If no exact match
is found, a generic hint is shown.

## Configuration

The plugin is configured in `.stylelintrc.json`:

```json
{
  "plugins": [
    "./scripts/stylelint-plugin-design-tokens/index.js"
  ],
  "rules": {
    "sculptor/no-hardcoded-values": true
  }
}
```

The rule only supports `true` as its primary option (enable/disable). There
are no secondary options.

## Running

The plugin runs as part of the standard lint pipeline:

```bash
# Run all linting (Python, JS/TS, SCSS including this plugin)
just lint

# Run only SCSS linting
cd sculptor/frontend && npm run lint:styles

# Auto-fix other stylelint rules (this plugin has no auto-fix)
just format
```

## Testing

Tests use Node's built-in test runner since stylelint is ESM-only and
incompatible with the project's Jest/Babel setup.

```bash
# From sculptor/frontend/
npm run test:stylelint-plugin

# Or directly
node --test scripts/stylelint-plugin-design-tokens/rule.test.mjs
```

The test suite covers all checked property categories, acceptance of
`var()`/`calc()` values, boundary conditions (e.g. `z-index: 5` vs
`z-index: 10`), multiple violations per declaration, and token suggestion
accuracy.

## Suppressing the rule

For intentional hardcoded values (e.g. one-off values with no token), use a
stylelint disable comment:

```scss
.example {
  font-size: 8px; // stylelint-disable-line sculptor/no-hardcoded-values -- no token for 8px
}
```
