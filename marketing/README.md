# Marketing demo pipeline

A repeatable pipeline for seeding a realistic Sculptor demo state and capturing
marketing screenshots. Everything runs against an **isolated, throwaway
Sculptor** — its own backend, fresh empty DB, headless Chromium, 2× screenshots
— so it never touches your real instance, repos, or GitHub.

```bash
just demo-seed          # boot the harness (if needed) + seed everything
source marketing/shots/control.sh   # then drive shots: click_testid / shot / ...
```

## How it works

1. **Clone** — every available demo repo is cloned fresh under the demo
   directory (default `~/.cache/sculptor-demo`), so seeded branches and worktrees
   never pollute a real checkout. Each clone's `origin` is rewritten to a
   github.com URL purely so the backend's PR polling engages; nothing ever
   contacts GitHub.
2. **Seed** — realistic state is scripted through deterministic
   [FakeClaude](../sculptor/sculptor/agents/testing/fake_claude.py) turns —
   real file diffs, commits, todo lists, canned command output — via the
   generated `sculpt` client. The harness relabels the FakeClaude agents via
   the `TESTING__FAKE_MODEL_DISPLAY_NAME` setting, so no screenshot ever says
   "Fake Claude".
3. **PR pills** — [`gh_shim/gh`](gh_shim/gh) sits at the front of the
   backend's PATH and answers the real PR-polling pipeline's `gh api graphql`
   calls from [`gh_fixtures`](seed/manifest.py) (see `PR_FIXTURES`), so open /
   merged PR pills render end-to-end through the shipped code path.
4. **Shoot** — named views are driven through the harness's HTTP control API
   ([`shots/control.sh`](shots/control.sh)).

Iterate by editing [`seed/manifest.py`](seed/manifest.py) (workspaces, turns,
PR fixtures), re-running `just demo-seed`, and re-shooting. The seed is
idempotent — repos are re-cloned and workspaces recreated — so it reproduces
the same state every run.

## Layout

```
marketing/
├── gh_shim/
│   └── gh                 # fake gh CLI: serves PR fixtures to the poller
├── seed/
│   ├── config.py          # demo dir + env knobs (single source of truth)
│   ├── repos.py           # fresh demo-dir clones with neutral identity + fake origin
│   ├── manifest.py        # every repo, workspace, scripted turn, PR fixture
│   ├── harness.py         # boot/ensure the QA harness with the demo env
│   ├── seed_all.py        # realize the whole manifest, idempotently
│   ├── seed_hero.py       # re-seed just the primary hero workspace
│   ├── induce_state.py    # refresh transient states (in-progress/waiting/error)
│   ├── fakeclaude.py      # helpers for fake_claude directives
│   └── harness_client.py  # sculpt-client access to the harness backend
├── shots/
│   └── control.sh         # sourceable browser-control helpers (locate/click/shot)
└── README.md
```

## Knobs (all optional)

| Env var | Default | Effect |
|---|---|---|
| `SCULPTOR_DEMO_DIR` | `~/.cache/sculptor-demo` | where clones, screenshots, ports, and fixtures live |
| `SCULPTOR_DEMO_REPO_OPENHOST` | unset | local path to clone the `openhost` sidebar-dressing repo from |
| `SCULPTOR_DEMO_REPO_MNGR` | unset | local path to clone the `mngr` sidebar-dressing repo from |
| `HARNESS_BACKEND_PORT` | unset | talk to an explicit backend instead of the harness port file |

The `sculptor` repo always clones from the checkout you run the pipeline in,
so `just demo-seed` works with zero configuration — the extra repos just add
sidebar variety when you have them.

## Gotchas

- `sculpt`'s ambient `SCULPT_API_PORT` points at your **real** instance;
  `harness_client` strips all ambient `SCULPT_*` vars and only ever uses the
  harness's port file. Never seed with a bare `sculpt` command.
- This directory is deliberately outside the linted product tree: excluded
  from ratchets (`.ratchetignore`) and shellcheck, and not covered by the
  ruff/pyrefly scopes. Match the house style by hand.
- The waiting-on-question (amber) state is held by a long scripted
  `timeout_seconds` on the ask directive; the in-progress and error states
  decay — re-run `induce_state.py` right before capturing them.
