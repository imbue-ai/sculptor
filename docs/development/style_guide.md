# Style Guide

Use consistent patterns. Use tools to enforce consistency. See [linting](./linting.md) for how we enforce this.

For specific frontend/backend style guides, see the following:
- [frontend style guide](style/frontend.md)
- [backend style guide](style/backend.md).

## Comments

Write comments for the future reader who opens the file cold, with no knowledge
of the change that introduced them. A comment explains what the present code does
and why it is shaped this way — including timeless "don't do X, because Y"
guardrails — in the present tense.

Do not narrate the change itself: avoid "the old code did X", "this used to be
Y", "we changed this because…", the bug that prompted the edit, or a ticket ID.
That history lives in the commit message, the PR description, and `git blame`,
not in the source, where it only goes stale.

Litmus test: if a comment would read as confusing or misleading once its PR is
ancient history, it is grounded in the task — rewrite it to stand on its own.
Reframe history as present-tense rationale: "we used to key on `head_ref` and
main builds ran concurrently" becomes "`head_ref` is empty on push events, so
key on `github.ref`".
