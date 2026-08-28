# Style Guide

Use consistent patterns. Use tools to enforce consistency. See [linting](./linting.md) for how we enforce this.

For specific frontend/backend style guides, see the following:
- [frontend style guide](style/frontend.md)
- [frontend file structure](style/frontend_structure.md)
- [backend style guide](style/backend.md).

## Comments

Write comments for the future reader who opens the file cold, with no knowledge of the change that introduced them. A comment explains what the present code does and why it is shaped this way — including timeless "don't do X, because Y" guardrails — in the present tense.

Do not narrate the change itself: avoid "the old code did X", "this used to be Y", "we changed this because…", the bug that prompted the edit, or a ticket ID cited to explain why existing code changed. That backward-looking history belongs in the commit message, the PR description, and `git blame`, not in the source, where it only goes stale.

The exception is forward-looking, not historical: a `TODO`/`FIXME` may reference a tracking issue for planned work that hasn't landed yet, since that orients the future reader toward what's coming rather than rehashing what changed. This is the single carve-out — other guides inherit it and shouldn't add their own ticket-reference exceptions.

Litmus test: if a comment would read as confusing or misleading once its PR is ancient history, it is grounded in the task — rewrite it to stand on its own. Reframe history as present-tense rationale: "we used to key on `head_ref` and main builds ran concurrently" becomes "`head_ref` is empty on push events, so key on `github.ref`".

Don't let a comment litigate the code's correctness. A line that protests too much — "no race here, because the lock is held", "this can never be null", or a paragraph walking through why the algorithm is sound — usually betrays unease about the code rather than illuminating it for the next reader. Tests are where we assert that the code is correct; let them carry that weight. A comment should explain why the code is shaped the way it is, not argue that it works.

Don't mirror a sibling comment. Adding an inline comment to one branch, field, or helper merely because the neighboring one has it spreads noise instead of meaning — and the comment you are copying may itself be overdue for removal. Judge each comment on whether it earns its place, not on whether its neighbors have one.

Delete commented-out code outright rather than leaving it parked behind a comment. Version control already remembers it, and a dormant block only makes the next reader wonder whether it still matters.

Don't restate facts from the surrounding code that are apt to drift — the number of subclasses, the list of allowed variants, the call sites of a function. Such a comment pins itself to a single moment and goes stale as soon as the code moves on; follow DRY and let the code remain the single source of truth.

Skip ASCII-art banners and box-drawing section dividers. A plain one-line comment conveys the same thing without the visual noise, and the art only drifts out of alignment as the code around it changes.
