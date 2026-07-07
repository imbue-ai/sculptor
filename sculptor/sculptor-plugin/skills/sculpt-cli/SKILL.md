---
name: sculpt-cli
description: |
  Interact with Sculptor programmatically using the sculpt CLI.
  Use this skill when using `sculpt`, or when designing or planning a workflow
  that would benefit from understanding the structural capabilities of `sculpt`
  (workspaces, agents, isolation, and how code flows between them).
---

# Sculpt CLI

CLI for interacting with the Sculptor API. Use `sculpt --help` for full documentation.

## Identity: who am I?

Every Sculptor agent shell exports three env vars identifying the shell's own
context:

| variable             | meaning                          |
|----------------------|----------------------------------|
| `SCULPT_AGENT_ID`    | this shell's own agent (task) ID |
| `SCULPT_WORKSPACE_ID`| this shell's workspace ID        |
| `SCULPT_PROJECT_ID`  | the repo/project ID              |

Commands default to them where it makes sense:

```bash
sculpt agent show        # no argument: shows THIS shell's agent
sculpt agent status      # ditto
sculpt workspace show    # no argument: shows THIS shell's workspace
```

`sculpt agent list` / `sculpt workspace list` mark your own row with `*`, and
their `--json` output includes an `is_self` field. Before reasoning about
*other* agents, check your own identity first — don't infer it from branch
names or workspace titles.

## Addressing agents in other workspaces

Full agent IDs (and unambiguous prefixes) work from anywhere: `send`,
`interrupt`, `rename`, and `delete` resolve them across all workspaces.
`SCULPT_WORKSPACE_ID` only narrows ambiguous prefixes; when the agent lives
elsewhere a stderr note tells you which workspace it is in. An explicit
`--workspace` is authoritative — if the agent is not in that workspace, the
command errors instead of silently redirecting.

## Delegate-and-await: the core orchestration pattern

`--follow` on `run` and `agent send` streams the reply and **exits when the
turn ends**, so it is a synchronous request/response primitive — prefer it
over polling:

```bash
# Create a workspace + agent, stream until its first turn finishes
sculpt run --model haiku --strategy clone --name "Experiment" "Try X and report" -f

# Send a follow-up and wait for the answer
sculpt agent send <agent-id> "And what about Y?" -f
```

Exit codes for `--follow`: `0` = turn completed, `2` = the agent stopped to
ask a question (WAITING). For polling instead, call the single-shot
`sculpt agent status <id> --json` in your own loop.

## Models

`agent send` **keeps the agent's current model** unless you pass `--model` —
passing it switches the agent's model persistently for subsequent turns.
`run` / `agent create` default to opus; pick `--model haiku`/`sonnet` for
cheap disposable agents.

## Agents waiting on a question

When an agent calls AskUserQuestion its status becomes `WAITING`, and
`sculpt agent status` shows the question and its options:

```
Status: WAITING
Waiting: Which color?
Options: Red | Blue
```

(`--json`: `waiting_detail` + `waiting_options`.) **Answering is reserved for
the human user in the Sculptor UI** — there is deliberately no CLI answer
command. If you are orchestrating and must unblock the agent yourself,
`sculpt agent interrupt <id>` abandons the question, after which `send` works
again.

## JSON output

All commands support `--json` for machine-readable output. JSON goes to
stdout, informational notes to stderr, and with `--json` errors are emitted to
stderr as `{"error": ..., "detail": ...}`. Discover each command's exact output
shape with the `schema` subcommand:

```bash
sculpt schema                   # list all available schemas
sculpt schema agent.status      # JSON Schema for `sculpt agent status --json`
```

Examples:

```bash
# Get workspace IDs
sculpt workspace list --all --json | jq '.[].id'

# Get running agents
sculpt agent list --all --json | jq '[.[] | select(.status == "RUNNING")]'

# Get agent progress
sculpt agent status <id> --json | jq '{status, progress: "\(.task_completed)/\(.task_total)"}'
```

## Examples

```bash
# List repos and workspaces
sculpt repo list --json
sculpt workspace list --all --json

# Create a workspace
sculpt workspace create --name "My workspace" --json

# Create a workspace + agent in one step
sculpt run --model opus --name "Fix bug" "Fix the login bug" --json

# Show workspace/agent details
sculpt workspace show <id> --json
sculpt agent show <id> --json

# Send a message to an agent (any workspace; keeps the agent's model)
sculpt agent send <agent-id> "Please also update the tests" --json

# Clean up (both prompt unless -y)
sculpt agent delete <agent-id> -y
sculpt workspace delete <workspace-id> -y
```

## Conceptual model

A repo comprises workspaces (1:n). A workspace comprises agents (1:n).

### Repo

A path on the user's machine pointing at a git repository. `sculpt repo list`
shows these. This is the source-of-truth git state; everything else derives
from it.

### Workspace

A working environment derived from a repo. The **initialization strategy**
is fixed at creation and determines how the workspace's checkout relates to
the user's repo:

| strategy   | git relationship to user's repo                                            | good for                                    |
|------------|-----------------------------------------------------------------------------|---------------------------------------------|
| `clone`    | Separate clone with shared git object store; remotes mirrored. Isolated.    | disposable experiments, risky changes        |
| `worktree` | Real `git worktree`; `.git` shared. Commits land in user's repo instantly.  | normal feature work (the default)            |
| `in_place` | None — agent edits the user's actual checkout.                              | coordination tasks on the live checkout      |

### Finding a workspace's files

Workspace directories on disk are named by opaque internal IDs that do NOT
match the `ws_...` API ID — never guess paths. Use the fields reported by
`workspace show`/`list --json`:

- `working_directory` — the checkout directory (`.../code` for clone/worktree,
  the repo path itself for in_place)
- `current_branch` — the branch checked out there right now
- `repo_path` — the user's original repo

### Agent

A single coding agent running inside a workspace. Each agent has its own
conversation, status, todos, state, and artifacts — but shares the
workspace's checkout with every other agent in the same workspace.

### What multiple agents in one workspace share

**Shared**: every tracked and untracked file in the checkout, and git state
(HEAD, branches, working tree, index). There is **no file locking** between
sibling agents.

**Private to each agent**: conversation history; TODOs, status, current
activity; per-agent state and artifact directories.

## Using sculpt from outside a Sculptor shell

`sculpt` talks to the local Sculptor app, defaulting to
`http://localhost:5050`. If the app serves a different port (it exports
`SCULPT_API_PORT` into its own shells), set that variable or pass
`--base-url` explicitly.
