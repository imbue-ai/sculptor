# Design Review Rules

Review rules for design quality: does a change use our design system, follow the patterns already in the app, and hold the visual and copy bar we've set. The goal is a product that feels like one coherent thing — not a collection of screens built by different people at different times.

These checks are deliberately the ones a linter *can't* make. Our [stylelint plugin](../style/frontend.md#design-tokens) already rejects raw hardcoded values (`padding: 16px`, `#3d63dd`) — do **not** re-report those here. This doc is about the judgments a machine can't: whether the *right* token was chosen, whether an existing component should have been reused, whether the wording matches the rest of the UI. For component *correctness* (effects, state, refs, performance) see [`react.md`](react.md); for Sculptor data-flow conventions see [`sculptor.md`](sculptor.md); for the underlying token vocabulary see the [frontend style guide](../style/frontend.md#styling-css) and the `frontend-design-tokens` skill.

For each issue found, note the issue type, file/line, and a brief description of what is wrong and how to fix it.

---

## `prefer_radix_components`

**Question:** Is this hand-rolling something Radix Themes already provides — or dropping to raw elements plus CSS where a Radix component and its props would do the job?

Radix Themes (`@radix-ui/themes`) is our component foundation. Reaching for it first isn't just about less code — its components come with correct interactive states (hover, active, focus-visible, disabled), light/dark theme adaptation, sensible contrast, keyboard and ARIA behavior, and a shared set of `size` / `variant` / `color` / `gap` props. Every one of those is something you get for free by using the component and lose the moment you hand-roll a `<div onClick>` with bespoke CSS. Most of our "design quality" bar is upheld automatically *as long as you stay on Radix* — the failure mode this rule catches is code that steps off it. (Bypassing a *Sculptor* shared component built on top of Radix is the sibling rule, [`reuse_existing_components`](#reuse_existing_components) — file a finding under one or the other, not both.)

Follow the [styling hierarchy](../style/frontend.md#styling-hierarchy): Radix props first, then design tokens in SCSS modules, then (rarely) dynamic inline styles.

**What to look for:**
- A raw `<div>` / `<span>` with layout CSS (`display: flex`, `gap`, `padding`) where `<Flex>`, `<Box>`, or `<Grid>` and their props express the same thing
- A hand-built clickable element (`<div onClick>` with hover/active CSS) reimplementing `<Button>` / `<IconButton>` — it will be missing the focus ring, the disabled treatment, or the dark-mode color, because those aren't free off-Radix
- Custom `size` / `variant` styling that duplicates a prop the Radix component already exposes (e.g. a `.small` / `.ghost` SCSS class next to a component that takes `size="1"` / `variant="ghost"`)
- Raw `font-size` / `font-weight` in SCSS where `<Text size>` / `<Heading>` / `weight` would keep the type on-scale (see also [`text_presentation`](#text_presentation))
- An overlay, dropdown, tooltip, or dialog built from absolutely-positioned `<div>`s instead of the Radix primitive — usually also a portal / focus-trap / z-index bug waiting to happen

```tsx
// Bad: off-Radix — no focus ring, no disabled state, dark mode unaddressed
<div className={styles.iconButton} onClick={handleClose}>
  <XIcon />
</div>

// Good: on-Radix — states, theming, and a11y come for free
<IconButton variant="ghost" size="2" onClick={handleClose} aria-label="Close">
  <XIcon />
</IconButton>
```

**Exceptions:** Leaf presentational details Radix genuinely doesn't cover belong in SCSS modules with tokens. The rule is about *reaching past* an available component, not about the SCSS you legitimately need underneath one.

---

## `use_correct_tokens`

**Question:** Does this use the *right* token — not merely *a* token?

Stylelint guarantees a value is a token; it can't tell whether it's the correct one. This rule is the semantic layer on top: the right token for the meaning, from the right scale, at the right step.

**What to look for:**
- **Semantic token bypassed:** a raw scale value where a named semantic token in [`tokens.css`](../../../sculptor/frontend/src/styles/tokens.css) describes that exact usage — `border: 1px solid var(--gray-6)` on a terminal surface when `--terminal-border` exists; a hardcoded indigo where `--button-primary-bg` is the named token. Semantic tokens are the single point of retuning; raw scale values drift away from them.
- **Wrong scale step:** Radix's 12-step scales are semantic — steps `1–2` are app backgrounds, `3–5` component backgrounds, `6–8` borders/separators, `9–10` solid fills, `11–12` text. `color: var(--gray-3)` for body text fails contrast by construction; `background: var(--gray-11)` for a subtle surface is far too heavy.
- **Ad-hoc z-index:** any `z-index` literal instead of the `--z-*` scale — and the *wrong tier* within it (a dropdown that must sit under a modal but uses `--z-modal`).
- **Ad-hoc motion:** `transition: 0.2s ease` instead of `--duration-*` with `--ease-*`.
- **Ad-hoc elevation:** a hand-mixed `rgba` shadow instead of `--shadow-*`, so it drifts from the elevation system.
- **Magic values in JS:** literal pixel numbers or colors in a dynamic `style={{ ... }}` object or a JS calculation — stylelint only sees SCSS, so this is the gap it can't cover. A hardcoded `rgba(...)` here is doubly wrong: off-token *and* blind to light/dark theme switching.

```scss
/* Bad: a token, but the wrong one — raw scale where a semantic token exists,
   an off-scale text step, and an ad-hoc transition */
.banner {
  border: 1px solid var(--gray-6);
  color: var(--gray-5);
  transition: opacity 0.2s ease;
}

/* Good: right token for the meaning, right step, motion tokens */
.banner {
  border: 1px solid var(--terminal-border);
  color: var(--gray-11);
  transition: opacity var(--duration-normal) var(--ease-default);
}
```

**Fix:** Reach for the semantic token first; fall back to the raw scale only when no semantic token names the usage, and pick the step that matches Radix's scale semantics.

---

## `reuse_existing_components`

**Question:** Does a shared component in `sculptor/frontend/src/components/` already do this?

This is the design counterpart to [`reuse_existing_data_hooks`](sculptor.md#reuse_existing_data_hooks). We have a deep library of shared components already built on Radix. A bespoke reimplementation fragments the system: it won't inherit the shared component's variants, theming, or a11y behavior, and it silently drifts on the next design change while the canonical one moves on without it. Where [`prefer_radix_components`](#prefer_radix_components) catches stepping off the Radix layer, this rule catches ignoring our own shared layer built on top of it.

**What to look for:**
- A new popover / menu / dialog / tooltip / card / status indicator when a shared one already exists (check `components/` before building)
- A shared component wrapped in extra CSS to imitate an appearance it already exposes as a prop or variant
- Two structurally-similar components added in the same change that should have been one parameterized component

**Fix:** Use the existing component. If it's close but not quite right, extend it (add a variant / prop) rather than forking a parallel copy. Before adding anything new, grep `components/` for the noun you're about to build.

---

## `follow_existing_design_patterns`

**Question:** Does this match the nearest analogous UI already in the app, or does it invent a new structure for a problem we've already solved?

Consistency is a feature. When a new panel, row, section, or form doesn't match how its siblings are built, users feel the seam even if they can't name it — different spacing rhythm, a different header layout, a different way of laying out the same kind of content.

**What to look for:**
- A new panel / section that doesn't build on the existing layout scaffold the app uses for that surface — panel chrome lives in [`components/panels/`](../../../sculptor/frontend/src/components/panels/) (e.g. `PanelHeader`), and for anything else the sibling sections are the reference
- Spacing between elements that doesn't match the rhythm of the analogous UI next to it — a new `gap` / `padding` value where a sibling already established one
- A list row, empty state, or header laid out differently from the existing rows / empty states / headers of the same kind
- A form or dialog whose field layout, button order, and affordances diverge from the established pattern for the same interaction
- Content that breaks when its container narrows — Sculptor's panels are resizable, so new UI should degrade the way its siblings do (truncate, wrap, or collapse) rather than overflow or clip

```tsx
// Bad: sibling panels use the shared header and gap="2"; this one invents
// its own header markup and spacing rhythm
<Flex direction="column" style={{ gap: 14 }}>
  <Text size="3" weight="bold">Recent changes</Text>
  ...
</Flex>

// Good: same scaffold, same rhythm as the panels beside it
<Flex direction="column" gap="2">
  <PanelHeader title="Recent changes" />
  ...
</Flex>
```

**Fix:** Find the closest existing equivalent, and match its structure, spacing, and affordances. Diverge only when there's a real reason the pattern doesn't fit — and make that reason explicit.

---

## `use_lucide_icons`

**Question:** Is this icon from `lucide-react`, at a consistent size and stroke — and does the same icon mean the same thing it means elsewhere?

`lucide-react` is our icon set (the dominant source across the app). A stray icon from another library, an inline hand-drawn SVG, or the same glyph used for two unrelated actions makes the iconography feel incoherent.

**What to look for:**
- An icon imported from `@radix-ui/react-icons` or another library, or an inline `<svg>`, where a `lucide-react` equivalent exists
- An icon sized with an ad-hoc pixel value instead of matching the size of icons in the same context
- The same glyph used for two different meanings, or two different glyphs used for the same action across the app (e.g. trash in one place and an X in another for "delete")

**Fix:** Import from `lucide-react`, size it to match its neighbors, and keep one icon per meaning across the product.

**Exceptions:** A handful of `@radix-ui/react-icons` usages predate the convention; don't churn them gratuitously, but new icons should be lucide.

---

## `status_colors_convey_meaning`

**Question:** Does color carry the meaning it always carries in the app — and do dangerous actions get the danger treatment?

The linter confirms `var(--red-9)` is a token; it can't tell whether red is the *right* meaning here. We use color semantically — red for danger / errors, green for success, amber for warnings — and that mapping only works if it's applied consistently. This is a distinct lens from [`use_correct_tokens`](#use_correct_tokens): that rule is "right variable," this one is "right meaning."

**What to look for:**
- A destructive action (delete, remove, discard) that isn't rendered with the danger color (`color="red"` / the red scale) — it reads as ordinary and invites misclicks
- A destructive action with no confirmation step, where sibling destructive actions confirm
- Red / green / amber used decoratively for something that isn't an error / success / warning, diluting the signal
- Success or error feedback that uses an arbitrary color instead of the established green / red

```tsx
// Bad: an irreversible action that looks like any other button
<Button onClick={handleDelete}>Delete workspace</Button>

// Good: danger color + a confirmation, matching sibling destructive actions
<Button color="red" onClick={handleDeleteWithConfirm}>Delete workspace</Button>
```

**Fix:** Map the action to its meaning — danger actions get the red treatment and a confirmation; reserve green / amber for genuine success / warning. Match how the nearest existing action of the same kind is treated.

---

## `text_presentation`

**Question:** Is text rendered through the right component, the shared formatters, and the right overflow behavior — or hand-rolled?

This is about how text is *presented* (its wording is [`voice_and_tone`](#voice_and_tone)). Presentation should stay on the type scale and reuse shared helpers, so type, numbers, dates, and truncation look the same everywhere.

**What to look for:**
- **Off-scale type:** raw `font-size` / `font-weight` in SCSS where `<Text size>` / `<Heading>` / `weight` props keep it on the scale
- **Secondary text via opacity:** de-emphasized text using `opacity:` instead of `color="gray"` (or a muted token) — the app overwhelmingly uses `color="gray"` for this; opacity dims inconsistently against different backgrounds
- **Hand-rolled formatting:** inline date / time / duration / relative-time strings instead of the shared helpers ([`formatRelativeTime.ts`](../../../sculptor/frontend/src/common/formatRelativeTime.ts), [`timestampUtils.ts`](../../../sculptor/frontend/src/pages/workspace/components/chat-alpha/timestampUtils.ts), [`durationUtils.ts`](../../../sculptor/frontend/src/pages/workspace/components/chat-alpha/durationUtils.ts)); ad-hoc pluralization or number formatting
- **DIY truncation:** a SCSS `text-overflow: ellipsis` block where the Radix `<Text truncate>` prop does it
- **Code / paths / IDs not monospaced:** file paths, commit hashes, and IDs rendered in the body font instead of the monospace convention
- **Misaligned numerals:** changing counters / timers laid out in a column without `tabular-nums`, causing width jitter as digits change

```tsx
// Bad: off-scale, secondary-via-opacity, hand-formatted time
<div className={styles.metaSmallFaded}>{`${minsAgo} minutes ago`}</div>

// Good: on-scale Text, muted via color, shared formatter
<Text size="1" color="gray">{formatRelativeTime(timestamp)}</Text>
```

**Fix:** Use `<Text>` / `<Heading>` with `size` / `weight` / `color` props, the shared formatter for the data type, `truncate` for overflow, and the monospace treatment for code-like strings. Check `src/common/` and the chat-alpha `*Utils.ts` files linked above before writing a new formatter.

---

## `voice_and_tone`

**Question:** Is user-facing copy — button labels, menu items, tooltips, dialog titles, empty states, error messages — worded the way the rest of the product words things?

This is about the *words*, not their pixels. A linter can't judge copy; a design reviewer must. Inconsistent wording makes the product feel like it was assembled from parts.

**What to look for:**
- **Buttons name the action, imperative:** `Create workspace`, not `Workspace creation`, `OK`, `Submit`, or `Yes`. A confirm button states the specific action (`Delete workspace`) so it reads correctly on its own.
- **Casing:** sentence case for labels, buttons, and headings — not Title Case or ALL CAPS (barring an established exception).
- **Terminology drift:** one word per concept across the whole UI — not `Delete` here and `Remove` there for the same action, nor `workspace` / `session` / `branch` used interchangeably. Match the product's established vocabulary.
- **Conciseness:** no `Click here`, no filler `Please…`, no restating the obvious; labels as short as they can be while staying unambiguous.
- **Error & empty states:** say what happened and what to do next, in plain language — not a raw error code, stack detail, or internal jargon (`ENOENT`, `null workspace`).
- **Tone:** calm and direct; nothing cutesy or alarmist that clashes with neighboring copy.

```tsx
// Bad: vague label, Title Case, generic confirm
<Button>Workspace Creation</Button>
<AlertDialog.Action>Yes</AlertDialog.Action>

// Good: imperative + specific, sentence case
<Button>Create workspace</Button>
<AlertDialog.Action>Delete workspace</AlertDialog.Action>
```

**Fix:** Match the wording, casing, and terminology of the nearest existing equivalent UI. When naming a new concept, grep for how it's already referred to and reuse that term.

**Exceptions:** Established proper nouns and product terms keep their canonical casing (`GitHub`, `Sculptor`).

---

## `accessible_icon_only_controls`

**Question:** Does every icon-only control have an accessible name?

An icon-only button with no text label is invisible to screen readers and unlabeled in tests unless it carries an accessible name. A `Tooltip` helps sighted users discover the action, but it does not *name* the control for assistive tech — the accessible name comes from `aria-label` (or visible text). New icon-only controls should carry both where sibling controls do.

**What to look for:**
- An `<IconButton>` (or any clickable icon-only element) with no `aria-label` and no wrapping `<Tooltip>`
- A control whose only content is a `lucide-react` icon and whose purpose isn't announced anywhere
- A `Tooltip` relied on as the only label — a tooltip is a hover hint, not a substitute for an `aria-label`

```tsx
// Bad: no accessible name — unlabeled for screen readers and tests
<IconButton variant="ghost" onClick={handleCopy}>
  <CopyIcon />
</IconButton>

// Good: labeled (and a Tooltip for sighted users where the app uses them)
<Tooltip content="Copy to clipboard">
  <IconButton variant="ghost" onClick={handleCopy} aria-label="Copy to clipboard">
    <CopyIcon />
  </IconButton>
</Tooltip>
```

**Fix:** Give the control an `aria-label` describing the action (and a `Tooltip` where sibling controls have one). Keep the label wording consistent with [`voice_and_tone`](#voice_and_tone).

**Exceptions:** When the missing name traces to a shared component (a wrapper that renders the tooltip but no `aria-label`), file one finding against the component rather than one per call site — fixing it there labels every usage at once.
