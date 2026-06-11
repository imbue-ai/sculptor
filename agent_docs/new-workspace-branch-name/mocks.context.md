---
name: New workspace branch name UX
description: Mock context for redesigning how the branch name field is rendered inside the New Workspace modal — the existing inline pill input feels awkward and over-foregrounded.
type: project
---

# New Workspace Branch Name — Mock Context

## Description

The current New Workspace modal renders the branch name as an inline
text-input "pill" in the same row as the source-branch and mode dropdowns.
It auto-fills with a server-derived slug from the workspace title, shows a
"reset" link when overridden, displays a collision error below, and a
"required" hint when blank in worktree mode.

This rendering feels off:

- Visually it mimics the dropdown pills, but it's the only true text input
  in the row — the affordance is ambiguous.
- The auto-fill is opaque: the user sees a value they didn't type and
  doesn't always realize it's editable.
- The pill grows/shrinks with content, so the row feels jumpy.
- Loading dots, "required" hint, "reset" link, and collision error all
  pile around a small surface.
- For most users the auto-name is fine — surfacing it this prominently
  over-foregrounds an edge case.

The user asked to think through the right UX (where it should live, how it
should appear) and produce 6 mockups. Five should preserve the rest of the
modal as-is; one is permitted to reimagine the modal from scratch.

## Decisions

- **Direction: Variant 4 — Prefix slug pill.** Keep the existing pill row
  layout; replace the single editable input with a composite pill that
  renders a fixed author prefix (e.g. `ehsan/`) on the left and an
  editable suffix on the right. The two segments share one bordered
  pill, but the prefix is visually demoted (different background,
  subdued color) so it reads as non-editable.
  - Width feels stable because the suffix dominates the pill's growth,
    not the whole branch path.
  - Reduces what the user has to type and prevents accidental deletion
    of the convention.
  - Collision error rides inline as a small caption next to the pill;
    no row reflow.

## Rejected Alternatives

- **Variant 1 (disclosure line).** English-prose treatment is nice but
  the inline transform between read and edit modes makes the affordance
  too quiet and adds state to a small surface.
- **Variant 2 (title annotation).** Pulls the branch name into the
  body where it competes with the title/prompt. The branch name is a
  property of "where", not a caption on "what".
- **Variant 3 (chip + popover).** A popover is too heavy for a single
  short string and adds a dismissal step every time the user wants to
  override.
- **Variant 5 (footer summary).** Co-locating with the Create button is
  appealing as a "what will happen" strip, but it pulls the editable
  surface too far from the related "from / mode" pills.
- **Variant 6 (source sheet rebuild).** Reframes the modal as a
  spec/settings sheet. Heavier change than the user wanted —
  rest-of-modal preservation was a soft constraint.

## Tweaks Log

- Initial generation: produced 6 variants —
  1. Disclosure: collapse to a single "Branch: foo · edit" line; click
     reveals the input.
  2. Title-annotation: drop branch out of pills entirely; show as quiet
     gray subtitle under the workspace title with a click-to-edit link.
  3. Read-only chip + popover: chip in pills row shows the resolved name;
     clicking opens a focused popover containing the input, reset, and
     collision feedback.
  4. Prefix-slug pill: composite pill renders `from main → ehsan/<input>`
     where the author prefix is fixed and only the suffix is editable.
  5. Footer summary line: move branch name out of the pill row to a quiet
     "Branch: …" line in the footer above the Create button, with rename
     affordance.
  6. Reimagined Source sheet: full restructure — replace the pill row with
     a key/value "Source" panel (Repo / From / Mode / New branch) where
     each row is click-to-edit.
- Round 1 review:
    Requested: Pick the direction; user confirmed variant 4 and indicated no further tweaks.
    Changed: Promoted variant 4 to Decisions; moved variants 1/2/3/5/6
      to Rejected Alternatives with one-line rationales each. Variants
      remain in mocks.html as a historical record.
