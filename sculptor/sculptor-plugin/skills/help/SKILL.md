---
name: help
description: Ask any question about Sculptor.
when_to_use: |
  Invoke when the user asks how Sculptor works, how to use a Sculptor feature
  (workspaces, agents, code review, actions, slash commands), or a general
  "what is Sculptor" question. Fetches the latest docs from
  github.com/imbue-ai/sculptor rather than relying on training data.
user_invocable: true
---

# Sculptor Help

ARGUMENTS: $ARGUMENTS

The docs live in `imbue-ai/sculptor`. This skill ships inside the Sculptor app
and fetches the docs at runtime, so always pull the live files (with `curl`, not
WebFetch — we need the raw markdown, not an AI summary) and answer from them.

## Step 1 — detect the docs layout

The repo's layout changed when Sculptor was open-sourced: the help docs moved
from the repo root into `docs/help/`. Detect which layout is live before
fetching, so this skill keeps working across that transition:

```bash
curl -s -o /dev/null -w '%{http_code}' \
  https://raw.githubusercontent.com/imbue-ai/sculptor/main/docs/help/README.md
```

- `200` → **current layout**: index and pages live under `docs/help/`.
- anything else → **legacy layout**: index at the repo root, pages under `docs/`.

| | Current layout (`docs/help/`) | Legacy layout (flat) |
|---|---|---|
| Index (TOC) | `docs/help/README.md` | `SUMMARY.md` |
| Page | `docs/help/<page>.md` | `docs/<page>.md` |

## Step 2 — fetch and answer

Fetch the index, then the relevant page(s) at the matching base path. For
example, in the current layout:

```bash
curl -fsSL https://raw.githubusercontent.com/imbue-ai/sculptor/main/docs/help/README.md
curl -fsSL https://raw.githubusercontent.com/imbue-ai/sculptor/main/docs/help/<page>.md
```

The index lists each page by its relative path — mostly bare filenames like
`workspaces.md`, though some live in subfolders (e.g. `experimental/`). Resolve
each against the base path you chose in Step 1. Answer the user's question from
the page contents. If the docs don't cover it, link to the
[full docs](https://github.com/imbue-ai/sculptor/tree/main/docs/help).

## Response guidelines

### First-time user intro

If the user's prompt matches any of these patterns:

- "I just set up Sculptor for the first time"
- "What should I know to get started?"
- "Tell me about Sculptor"
- No arguments / empty prompt
- First message in a fresh conversation
- Any phrasing that suggests the user is new to Sculptor

Then respond with a **short, welcoming intro** (fits on one screen — no
scrolling). Use the live docs you fetched to fill in accurate details, but follow
this structure:

1. **One-line welcome.** Say what Sculptor is in a sentence.
2. **Core concepts** — cover these briefly (2-3 sentences each, max):
   - **Workspaces**: isolated clones of the user's repo — changes never touch the
     original until merged.
   - **Agents**: AI coding assistants that run inside workspaces. Multiple can run
     in parallel, but they share the workspace filesystem.
   - **Code review**: how to review and merge agent changes back (PRs, push/pull).
3. **Follow-up prompt**: tell the user — Want to learn more? Run `/sculptor:help`
   and ask a question.
4. **One link**: point to the full docs at
   `https://github.com/imbue-ai/sculptor/tree/main/docs/help`.

Constraints:

- **Keep it short.** The entire response must fit on one screen without
  scrolling. Aim for ~150-200 words.
- **No slash commands, actions, or panel details** in the intro — those are
  follow-up topics.
- **Only one link** (the docs). All sub-pages are reachable from there.
- **Do NOT reproduce this template verbatim.** Use the live docs to fill in
  current, accurate details. The structure above is a guideline, not a script.

### All other questions

For any other question, fetch the relevant page(s) listed in the index and answer
based on the docs. Keep answers concise and link to the docs if the user wants to
read more.
