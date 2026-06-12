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

## JSON output

All commands support `--json` for machine-readable output. To discover the exact
shape of the JSON each command returns, use the `schema` subcommand:

```bash
# List all available schemas
sculpt schema

# Show the JSON schema for a specific command's output
sculpt schema workspace.list
sculpt schema agent.show
sculpt schema run
```

The schema output is valid JSON Schema and can be used with `jq` for scripting:

```bash
# Get workspace IDs
sculpt workspace list --all --json | jq '.[].id'

# Get running agents
sculpt agent list --all --json | jq '[.[] | select(.status == "RUNNING")]'

# Get agent progress
sculpt agent status <id> --json | jq '{status, progress: "\(.todo_completed)/\(.todo_total)"}'
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

# Check agent status
sculpt agent status <id> --json

# Send a message to an agent
sculpt agent send <id> "Please also update the tests" -w <workspace_id> --json
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

| strategy   | working directory                       | git relationship to user's repo                                            |
|------------|-----------------------------------------|----------------------------------------------------------------------------|
| `clone`    | `~/.sculptor/workspaces/<wsid>/code/`   | Separate clone with shared git object store; remotes mirrored. Isolated.   |
| `worktree` | `~/.sculptor/workspaces/<wsid>/code/`   | Real `git worktree`; `.git` shared. Commits land in user's repo instantly. |
| `in_place` | The user's repo path itself             | None — agent edits the user's actual checkout.                             |

### Agent

A single coding agent running inside a workspace. Each agent has its own
conversation, status, todos, state, and artifacts — but shares the
workspace's `code/` directory with every other agent in the same workspace.

### Filesystem layout (clone / worktree)

```
~/.sculptor/workspaces/<workspace-id>/
├── code/                              # the checkout — SHARED across all agents
├── state/tasks/<agent-id>/            # per-agent private state
├── artifacts/tasks/<agent-id>/        # per-agent diffs, logs, etc.
└── attachments/                       # workspace-wide attachments
```

For `in_place`, the working directory is the user's repo path; the workspace
dir holds only per-agent state and artifacts.

### What multiple agents in one workspace share

**Shared**:

- Every tracked and untracked file in `code/`
- Git state: HEAD, branches, working tree, index

There is **no file locking** between sibling agents.

**Private to each agent**:

- Conversation history
- TODOs, status, current activity
- `state/tasks/<agent-id>/` and `artifacts/tasks/<agent-id>/`
