---
name: update-review-rules
description: |
  Add a new issue type to one of Sculptor's review-rule docs.
  Use when you've encountered a class of bugs, anti-patterns, or flaky
  test patterns that should be caught in future reviews.
---

# Add a Review Rule

Add a new issue type to one of Sculptor's review-rule docs to prevent a class of issues from recurring.

The three review-rule docs:
- **`docs/development/review/react.md`** — generic React rules that would apply in any React codebase: effects, state, refs, render purity, performance, props, lists.
- **`docs/development/review/sculptor.md`** — Sculptor-specific frontend conventions: backend data hooks (WS-pushed atoms, HTTP-pulled TanStack queries), Jotai atom usage, component-level invariants tied to our codebase.
- **`docs/development/review/integration_tests.md`** — Sculptor integration test rules: Playwright assertion patterns, test isolation, POM usage, flaky-pattern avoidance.

## Input

The user provides a description of the problem — this could be:
- A bug they just fixed and want to prevent in the future
- A code pattern they noticed during review that should be flagged
- A flaky test or test pattern that should be caught earlier
- A link to a file/line or diff that demonstrates the issue

## Steps

1. Read all three review docs (`docs/development/review/react.md`, `docs/development/review/sculptor.md`, `docs/development/review/integration_tests.md`) to understand the existing rules, their format, and their naming conventions.
2. Decide which file the new rule belongs in:
   - If the rule is about Playwright tests, integration test patterns, or test isolation/structure → `integration_tests.md`.
   - If the rule references Sculptor-specific frontend hooks, atoms, file paths, or our data-flow conventions (e.g. `useUnifiedStream`, `BackendQueryResult`, `workspaceAtomFamily`) → `sculptor.md`.
   - If the rule is purely about React's framework primitives and would apply in any React codebase → `react.md`.
   - When in doubt for frontend rules, prefer `sculptor.md` over `react.md`; revisit if the rule turns out to be more generic than expected.
3. Determine whether an existing rule already covers the issue (check all three docs). If it does, tell the user which rule covers it and ask if they'd like to refine that rule instead. Do not add a duplicate.
4. Draft a new rule following the exact format of existing rules in the chosen file.

   For `react.md` and `sculptor.md` (flat list, `## rule_name` headings):

   ```markdown
   ---

   ## `snake_case_rule_name`

   **Question:** A yes/no question that a reviewer can ask about the code.

   One or two paragraphs explaining why this is a problem and what the correct approach is.

   **What to look for:**
   - Concrete pattern or code smell to search for
   - Another pattern

   **Fix:** (optional) Brief description of how to fix it.

   **Exceptions:** (optional) Cases where this pattern is acceptable.
   ```

   For `integration_tests.md` (sectioned, `### rule_name` inside an existing `## Section`):

   ```markdown
   ---

   ### `snake_case_rule_name`

   **Question:** ...

   [rest is the same as above, but the heading is `###` and the rule lives
   under one of the existing `## Section` groupings — pick the section that
   matches the rule's topic, e.g. "Playwright Assertions", "Test Isolation",
   "Test Structure"]
   ```

5. Choose a clear `snake_case` name that describes the problem (not the fix). Follow the naming conventions:
   - Use `no_` prefix for patterns that should not exist (e.g., `no_effect_chains`, `no_sleep_then_assert`)
   - Use `use_` prefix for prescriptive positive patterns (e.g., `use_derived_atoms`, `use_expect_not_assert`)
   - Use a descriptive noun/adjective for structural issues (e.g., `monolithic_component`, `unstable_list_keys`)

6. Write the rule to be **generic** — it should describe a *class* of issues, not a single instance. Strip out details specific to the user's particular bug (component names, variable names, business logic, Linear ticket IDs). For `sculptor.md` and `integration_tests.md` rules, naming our codebase concepts is fine (and expected); for `react.md` rules, the content should apply in any React codebase. The "What to look for" section should describe concrete, recognizable patterns a reviewer can spot in code.

7. Only include code examples when absolutely necessary. Lean on the description, explanation, and "What to look for" patterns to convey the rule. The rule should be self-contained without code. Test rules sometimes benefit more from a "Bad/Good" pair because Playwright APIs are pattern-heavy.

8. Place the new rule near related rules in the chosen file. Use your judgement — group it with rules about similar topics (effects, state, atoms, refs, performance, Playwright assertions, test isolation, etc.).

9. Show the user the new rule (and which file you're adding it to) and ask for confirmation before writing it to the file.
