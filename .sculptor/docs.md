# Docs

Locations and operational config for the sculptor-workflow skills.
Document structure (spec sections, architecture sections, mock
conventions, plan layout) is baked into the skills — not configured
here.

## Spec Location
- **Path pattern:** `agent_docs/<slug>/spec.md`

## UI Reference

<!--
  Tell the `/sculptor-workflow:mock` skill how to match the app's
  visual style.
-->

- **Mock starter template (START HERE):** copy
  `.sculptor/mock_templates/sculptor-shell.html` — a self-contained
  starter with the app's exact dark tokens, fonts, app-shell backdrop,
  and dialog components, verified against live app captures. See
  `.sculptor/mock_templates/README.md` for usage and the companion
  screenshot script.
- **Component library:** `sculptor/frontend/src/components/` (React
  + Radix UI primitives).
- **Design tokens / styles:** see the `/frontend-design-tokens` skill
  for the canonical token list (colors, spacing, typography).
- **Storybook:** stories live in `sculptor/frontend/src/` alongside
  components; see the `/storybook-screenshot` skill for previews.
- **Style guide:** `docs/development/style_guide.md` for code-level UI conventions.

## Code Review

The configured skill below is invoked for code-review passes by:
- `/sculptor-workflow:review` at the end of the full feature workflow.
- `/sculptor-workflow:fix-bug`'s self-review phase (Phase 4 interactive
  / Phase A4.5 autonomous), so a fix isn't considered done until its
  diff has been reviewed.

Skill: `/code-review-checklist`
