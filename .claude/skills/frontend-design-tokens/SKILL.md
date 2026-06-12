---
name: frontend-design-tokens
description: |
  Guide for using design tokens in the Sculptor frontend.
  Use when writing or reviewing CSS/SCSS to pick correct token variables.
---

# Frontend Design Tokens

When writing CSS/SCSS in the Sculptor frontend, use design tokens instead of hardcoded values.

## Where to Find Tokens

### Radix Built-in Tokens (spacing, font sizes, radius, colors, font weights)

Read the source of truth directly:

```
sculptor/frontend/node_modules/@radix-ui/themes/tokens/base.css
```

This file contains all Radix CSS variables including:
- `--space-1` through `--space-9` (spacing)
- `--font-size-1` through `--font-size-9` (typography)
- `--font-weight-light`, `--font-weight-regular`, `--font-weight-medium`, `--font-weight-bold`
- `--radius-1` through `--radius-6`, `--radius-full` (border radius)

For color tokens, read the individual color files:

```
sculptor/frontend/node_modules/@radix-ui/themes/tokens/colors/*.css
```

These provide 12-step scales (e.g., `--gray-1` through `--gray-12`, `--accent-1` through `--accent-12`).

These are all loaded via `@radix-ui/themes/styles.css` which is imported in `Main.tsx`.

### Custom Tokens (animation, z-index, shadows, semantic colors)

Read our custom token definitions:

```
sculptor/frontend/src/styles/tokens.css
```

This defines tokens for things Radix does not provide.

### Radix Overrides

Global overrides to Radix component styles live in:

```
sculptor/frontend/src/styles/radix-overrides.css
```

### Global Styles

Brand colors, utility classes, and theming live in:

```
sculptor/frontend/src/index.css
```

## Rules

1. **Never hardcode** values that have a corresponding token or Radix variable
2. **Prefer Radix component props** (e.g., `<Flex gap="2">`) over `var()` when possible
3. **Use `var()` in SCSS modules** for values that can't be expressed through props
4. **No hex or rgb colors** in SCSS files -- use Radix color variables or semantic tokens

## Examples

```scss
/* Bad */
.card {
  padding: 16px;
  font-size: 14px;
  border-radius: 8px;
  transition: opacity 0.2s ease;
  color: #3d63dd;
}

/* Good */
.card {
  padding: var(--space-4);
  font-size: var(--font-size-2);
  border-radius: var(--radius-4);
  transition: opacity var(--duration-normal) var(--ease-default);
  color: var(--accent-9);
}
```

## Audit Script

Run to find style violations:

```bash
cd "sculptor/frontend" && npm run lint:styles
```
