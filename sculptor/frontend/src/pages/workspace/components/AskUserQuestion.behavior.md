# AskUserQuestion Component — Behavior Specification

This document defines the expected behavior for the `AskUserQuestion` component and serves as the specification for vitest coverage.

---

## 1. Rendering

### 1.1 Initial render
- Renders the header chip, question text, and all options for the first question.
- The first option row has the keyboard focus highlight (index 0) on mount.
- No option is selected on mount.
- The Submit button is **disabled** on mount (no answers yet).

### 1.2 Single-select questions
- Each option row has a **Radio** indicator (circle).
- The "Provide an alternative" row also has a Radio indicator.

### 1.3 Multi-select questions
- Each option row has a **Checkbox** indicator (square).
- The "Provide an alternative" row also has a Checkbox indicator.

### 1.4 Option text format
- The option label is rendered **bold** (semibold weight).
- If a description exists, it follows as `: description` on the same line (normal weight).
- If no description exists, only the bold label is shown.

### 1.5 "Provide an alternative" row
- When **not** selected, renders the label text in secondary/muted color.
- When **selected**, replaces the label with a textarea whose placeholder is `"Provide an alternative"`.

### 1.6 Navigation dots (multi-question only)
- Shown only when `questions.length > 1`.
- Four dot states (all accent-toned):
  - **Unfilled, not active**: small hollow circle with `--accent-7` border.
  - **Active, unfilled**: larger concentric ring (bullseye) using `--accent-11`.
  - **Answered, not active**: solid filled circle using `--accent-9`.
  - **Active, answered**: larger solid filled circle using `--accent-11`.
- Dots are clickable to navigate to that question.

### 1.7 No-dismiss variant
- When `onDismiss` is not provided, the Dismiss button is not rendered.

---

## 2. Single-select option selection

### 2.1 Clicking an option selects it
- Clicking an option row sets that option as the answer for the current question.
- The option's Radio indicator reflects the checked state.
- The row gets the `selected` highlight background.

### 2.2 Clicking another option deselects the previous one
- Only one option can be selected at a time.

### 2.3 Clicking a selected option does NOT deselect it
- Single-select has no toggle: clicking an already-selected option keeps it selected.

### 2.4 Selecting a predefined option deselects "Provide an alternative"
- If "Provide an alternative" was active, selecting a predefined option clears it (textarea disappears, label reappears).

---

## 3. Multi-select option selection

### 3.1 Clicking an option toggles it
- First click: selects the option (checkbox checked).
- Second click: deselects the option (checkbox unchecked).

### 3.2 Multiple options can be selected simultaneously
- Selecting option A then option B results in both being selected.

### 3.3 The answer value is a comma-separated string of selected labels
- Selecting "A" and "B" produces `"A, B"` as the answer.

### 3.4 Deselecting all options results in an empty answer
- The question is considered unanswered when no options are selected.

### 3.5 "Provide an alternative" coexists with other selections
- In multi-select, selecting "Provide an alternative" does not deselect other checked options.
- The typed text is appended to the comma-separated answer string.

---

## 4. "Provide an alternative" behavior

### 4.1 Activating "Provide an alternative"
- Clicking (or pressing Enter/Space on) the row activates it.
- The textarea automatically receives focus.
- The textarea is empty; placeholder text `"Provide an alternative"` is shown.

### 4.2 Typing in the textarea
- Typing sets the answer for the current question to the textarea's value.
- In single-select, the answer is exactly the typed text.
- In multi-select, the typed text is combined with any other selected options.

### 4.3 Textarea auto-resizes
- The textarea grows vertically as the user types multi-line text.

### 4.4 Escape from textarea
- Pressing Escape while the textarea is focused **blurs** the textarea and returns keyboard focus to the container.
- It does **not** dismiss the entire question form.
- After escaping, all arrow key navigation (Up/Down for options, Left/Right for question switching) works normally.

### 4.5 ArrowUp from textarea
- Pressing ArrowUp while the textarea is focused blurs the textarea and returns focus to the container, moving the highlight to the previous option.

### 4.6 ArrowDown in textarea
- Pressing ArrowDown while the textarea is focused does **not** exit the textarea; it allows native cursor movement within the textarea.

### 4.7 Empty textarea = unanswered (single-select)
- If the user activates "Provide an alternative" but types nothing, the question is considered unanswered and Submit stays disabled.

### 4.8 Deactivating "Provide an alternative" in single-select
- Clicking a predefined option while "Provide an alternative" is active deselects it (textarea disappears, label reappears).

### 4.9 Deactivating "Provide an alternative" in multi-select
- Clicking the row again unchecks it; the textarea disappears and the typed text is removed from the combined answer.

---

## 5. Vertical keyboard navigation (Up/Down)

### 5.1 ArrowDown moves focus to the next option
- Focus starts at index 0 (first option).
- Each ArrowDown increments the highlighted row by one.

### 5.2 ArrowDown from the last option wraps to the first option
- From "Provide an alternative" (last row), ArrowDown wraps back to the first option.

### 5.3 ArrowUp moves focus to the previous option
- Each ArrowUp decrements the highlighted row by one.

### 5.4 ArrowUp from the first option wraps to the last option
- From the first option, ArrowUp wraps to "Provide an alternative".

### 5.5 Enter/Space selects the focused option
- When an option row is highlighted, pressing Enter or Space toggles/selects that option.
- This includes the "Provide an alternative" row (which then activates the textarea).

### 5.6 Up/Down does NOT navigate to footer buttons
- Arrow keys only cycle through the option list; Dismiss and Submit are not reachable via arrow keys.

---

## 6. Horizontal keyboard navigation (Left/Right between questions)

### 6.1 ArrowRight advances to the next question
- Pressing ArrowRight when not on the last question moves to the next question.
- The option highlight resets to index 0.

### 6.2 ArrowRight on the last question does nothing
- No wrap-around.

### 6.3 ArrowLeft goes back to the previous question
- Pressing ArrowLeft when not on the first question moves to the previous question.
- The option highlight resets to index 0.

### 6.4 ArrowLeft on the first question does nothing
- No wrap-around.

### 6.5 Left/Right navigation is blocked while textarea is focused
- Pressing ArrowLeft or ArrowRight while the textarea is active does not switch questions (native cursor movement within textarea).
- After pressing Escape to exit the textarea, Left/Right navigation resumes normally.

### 6.6 Answers are preserved when navigating between questions
- Answering question 1, navigating to question 2, then navigating back to question 1 shows the previously selected answer.

### 6.7 Left/Right with a single question does nothing
- When there is only one question, ArrowLeft and ArrowRight have no effect.

---

## 7. Submit and dismiss behavior

### 7.1 Submit is disabled until all questions are answered
- With N questions, Submit is enabled only when every question has a non-empty answer.

### 7.2 Clicking Submit calls onSubmit with all answers
- `onSubmit` receives an object mapping each question string to its answer string.

### 7.3 Pressing Escape on the container calls onDismiss
- When keyboard focus is on the container (not in the textarea), Escape calls `onDismiss`.
- If `onDismiss` is not provided, Escape does nothing.

### 7.4 Cmd+Enter (or configured modifier) submits when all answered
- Works from the container and from inside the textarea.
- Does nothing if not all questions are answered.

---

## 8. Edge cases

| # | Behavior | Assumed |
|---|---|---|
| E1 | Enter on "Provide an alternative" when already selected and textarea has text | Keeps selected, re-focuses textarea |
| E2 | Multi-select: deactivate "Provide an alternative" then re-activate | Typed text is preserved in state |
| E3 | Cmd+Enter from inside the textarea | Submits if all answered |
| E4 | ArrowRight/ArrowLeft with only one question | No-op |
