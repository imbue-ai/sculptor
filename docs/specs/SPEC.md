# Sculptor — Product Specification

## 1. Overview

Sculptor is a desktop app for running coding agents in parallel — each in its own isolated copy of
your repository. Instead of handing your working tree to a single agent and waiting, you spin up as
many **workspaces** as you have tasks, point an **agent** at each, and let them work at the same
time while you review, steer, or start more.

The shape of the product is a short loop. You **connect a repo**, **create a workspace** (an
isolated copy of your code), and **prompt an agent** in chat. You watch it work — its messages, its
tool calls, and the changes it makes — and step in whenever you want: interrupt it, answer a
question it asks, or queue the next instruction. When it's done you **review the changes**, commit
them, and open a pull request, all without leaving the workspace. To explore a different task you
open another workspace; to collaborate on the same one you add another agent.

Sculptor runs entirely on your machine and offers the same capabilities two ways: a **desktop GUI**
for interactive work, and the **`sculpt` CLI** for driving the very same workspaces and agents
headlessly from a terminal, a script, or CI. On top of the basic loop it bundles a library of
**skills** — reusable, multi-step workflows like spec-then-build or test-driven bug fixing — that
run as their own agents.

Sculptor is an experimental research preview: it is under active development, it will have rough
edges, and it can change quickly.

## 2. Problem Statement

Coding agents are useful but awkward to run more than one at a time. Point an agent straight at your
working tree and it competes with you for the same files; run several and they trample each other
and your in-progress work. Keeping each agent's work on its own branch, reviewing what it did, and
getting it safely into a pull request are all manual. And the moment you want to automate any of
this — fan out a fleet of agents, or wire one into CI — a GUI-only tool runs out of room.

Sculptor exists to make running coding agents **parallel, isolated, reviewable, and steerable** the
default. It gives each agent an isolated copy of your repository so it can edit and run freely
without disturbing you; it makes the agent's changes first-class to review and commit; it keeps you
in control of what reaches the outside world; and it exposes everything through both a GUI and a
scriptable CLI. What it is *not* responsible for is being your editor, hosting your code, or serving
the models — it orchestrates agents over your local repositories.

## 3. Goals and Non-Goals

**Goals**
- Run multiple coding agents concurrently, each isolated from your checkout and from each other.
- Make agent work reviewable and safe to land: changes, diffs, commits, and PRs are first-class,
  and nothing reaches a remote without your action.
- Keep you in control of each agent: interrupt, steer, answer its questions, and recover your work
  across restarts and crashes.
- Offer the same capabilities headlessly via the `sculpt` CLI as in the GUI, so work can be scripted.
- Bundle reusable, multi-step workflows (skills) that take work from idea to shipped code.
- Run entirely on your machine, keeping your code private.

**Non-Goals**
- Not a general IDE or editor; it complements your editor rather than replacing it.
- Not a hosted, multi-tenant cloud service (the container/remote backend is experimental and still
  under your control).
- Not a model provider; it orchestrates agent CLIs (Claude, Pi), it doesn't serve models.
- Not a code host; your repositories and history stay yours.
- Not a finished, stable product — it is an experimental research preview.

## 4. Scenarios

A set of realistic, named end-to-end narratives — each a short story of a stereotypical user
accomplishing a real job.

**S1 — Fix a bug, test-first, without breaking stride.** Dana hits a rounding bug in the checkout
flow. She opens a workspace on a fresh branch off `main` and, rather than hand-write a prompt,
invokes **`/sculptor-workflow:fix-bug`** with "checkout total is off by a cent on multi-item carts."
The skill runs as its own agent and drives a **test-driven** fix: it first reproduces the bug with a
*failing* test, then changes the code until that test — and the rest of the suite — passes, narrating
each step as it goes. Dana goes back to her own editor while it works. A few minutes later she opens
the workspace's **Changes**, sees the new regression test sitting alongside the one-line fix, reads
the diff, commits, and opens a pull request — never having stashed or branched in her own checkout.
(For a bug she's already confident about, she could instead invoke
`/sculptor-workflow:fix-bug --autonomous` and let it run end-to-end and open the PR itself.)

**S2 — Compare two approaches in parallel.** Unsure which approach is better, Priya creates two
workspaces from the same starting branch and gives each agent the same task with a different steer
("smallest possible change" vs. "refactor for clarity"). The two agents run at the same time in
their separate copies; she watches both from their tabs, compares the resulting diffs, and keeps the
one she prefers — discarding the other workspace. (Two *workspaces*, not two agents in one: agents
sharing a workspace would edit the same files.)

**S3 — Drive a feature from spec to shipped.** Sam has a larger feature. He invokes
**`/sculptor-workflow:spec`**, which spawns a "Spec" agent that interviews him and writes an
implementation spec he watches take shape in the diff viewer. When it's right, he hands off down the
pipeline — each stage its own dedicated agent (renamed **Spec → Architect → Plan → Build**) that
produces a durable artifact the next stage reads: the architecture document, then a folder of
self-contained task files, then the built code committed task by task. (For a UI-heavy feature he'd
slot in **mock** near the start to generate interactive HTML mockups to react to first.) The pipeline
ends with **Review**: a final agent that checks the diff against the original spec, re-runs the tests,
and writes up its findings in `review.md` for Sam to act on. Each stage offers to hand off to the
next, so Sam can stop after any one, inspect its artifact, and resume the pipeline whenever he likes.

**S4 — Automate Sculptor from the terminal.** Alex lives at the keyboard, so he drives Sculptor with
the **`sculpt` CLI**: `sculpt run "regenerate the API client and fix any type errors" --follow`
creates a workspace *and* an agent in one command and streams the result; a wrapper script reads the
agent's status as JSON and, when it finishes, reads back the changes. Because both surfaces share one
**local** backend, that same workspace is sitting in the desktop app if Alex wants to take over
interactively — and conversely a workspace he started in the app is drivable from `sculpt`. This is
how he wires a routine repo chore into a local `Makefile` target or a personal cron job, and how he
fans several agents out from a single script. (Sculptor is a server running on *your* machine, so
`sculpt` automates the Sculptor you already have open — not a fresh one conjured inside an ephemeral
remote CI runner, which has no local backend or checkout to drive.)

**S5 — Run a fleet; let the dots route your attention.** Maya is mid-sprint with a dozen things in
flight at once. Three large features are each moving through the workflow skills in their own
workspaces; another seven or eight smaller bugs are each handed to a `fix-bug` agent in a workspace
of its own. She isn't watching any single one — she reads the **status dots** across the workspace
tabs as a dashboard of where her attention is owed: a *ready* dot means an agent has finished and
wants review, a *waiting* dot means one is blocked on a question or plan approval, an *error* dot
means one needs a human. She hovers a tab to **peek** at that workspace's agents, branch, PR status,
and diff stats without leaving the agent she's in, and uses **Cmd+P / Cmd+K** to jump straight to
whichever workspace is asking for her. She approves a plan here, reviews and commits a finished bug
fix there, unsticks a confused build agent — then drops back into her own work. The win isn't that
any single agent is faster; it's that Sculptor lets her keep ten-plus autonomous agents productive at
once by telling her exactly **where and when** to look, so nothing stalls silently and nothing
demands constant supervision.

**S6 — Ship a batch overnight with self-healing CI.** At the end of the day Raj clears a backlog of
well-understood bugs by firing off **`/sculptor-workflow:fix-bug --autonomous`** in a workspace each:
every one reproduces, fixes, verifies, and opens a pull request with no further input from him. He
turns on the **CI babysitter** so that when a PR's pipeline fails, Sculptor automatically asks an
agent to read the failure, fix it, and push — up to a configured retry cap — and to resolve simple
merge conflicts the same way. He leaves his machine running and steps away for the night (Sculptor is
a local server, so the agents and babysitter keep working only while his machine is on). By morning
most of the PRs are green and ready to merge; the handful the babysitter couldn't rescue are flagged
with an **error** or **waiting** dot for Raj to take over by hand. He spends the morning reviewing
diffs and merging — not babysitting pipelines.

The exhaustive, UI-level Given/When/Then list lives in `scenarios.md` (and `scenario_coverage.md`
maps those to tests); this section holds only the rich narratives.

## 5. System Overview & Components

This section is the **engineering view** — the one place implementation is described. Product
behavior is in §7/§9; the development and quality substrate is in §10.

Sculptor runs entirely on your machine as a small set of cooperating pieces arranged around a
**single local backend server**. Both product surfaces — the **Electron desktop GUI** and the
**`sculpt` CLI** — are clients of that one server, talking to it over HTTP for actions and
subscribing to a **live update stream** for state. There is no separate "CLI backend" and "GUI
backend": a **Workspace** or **Agent** created from the terminal appears in the desktop app and vice
versa, because both surfaces drive the same service and read the same persisted state. The backend
owns the domain — **Projects (Repos)**, **Workspaces**, and **Agents** — and is responsible for
shaping that domain into the view the surfaces render.

The desktop GUI is a **thin client**: it does almost no business logic of its own, instead rendering
backend-derived UI state that is pushed to it live (a full snapshot on connect, then deltas). To
keep the two surfaces from drifting from the backend, **TypeScript types and the API clients are
generated from the backend's models and OpenAPI spec**, so the contract is defined once on the
server and consumed everywhere. Underneath the domain, an **agent runner** supervises the actual
agent CLI process, an **isolation layer** gives each Workspace its own copy of the repo, and **local
persistence** records everything.

| Component | Responsibility |
|---|---|
| **Electron desktop GUI** (React) | Thin client that renders backend-derived UI state streamed live; sends user actions to the backend over HTTP. Built with React/Jotai/Radix, packaged via Electron Forge. |
| **`sculpt` CLI** | First-class headless surface (terminal, scripts, CI) for driving the same local Sculptor as the GUI. See §8. |
| **Local backend server** | The single local service both surfaces talk to — exposes the HTTP API and the live update stream, owns the Project/Workspace/Agent domain, and derives the shaped UI state the frontend renders. |
| **Agent runner** | Launches and supervises the underlying agent CLI (Claude or Pi) for each Agent, relaying its messages, status, and tool activity back through the backend. |
| **Isolation layer** | Backs each Workspace with an isolated copy of the repo — **worktree**, **clone**, or **in-place** — all running locally on your machine. |
| **Custom backend (experimental)** | An opt-in escape hatch that relocates the *whole* backend off-host: a user-supplied launcher command (e.g. Docker, SSH, a VM) that the app connects to over a printed URL. It is **not** a per-workspace isolation mode — it moves the entire service, not one workspace's checkout (→ §7.12, §9.1). |
| **Local persistence** | A local store (an append-only snapshot log plus a materialized current-state view, with versioned migrations) holding Projects, Workspaces, Agents, and conversation history. |

Deeper detail on how these pieces are built and operated lives in **§10 (Engineering Substrate)**;
the guarantees they uphold are spelled out in **§9**.

## 6. Core Domain Model

Sculptor's vocabulary is small and load-bearing; every feature in §7 is described in these terms.
This section names **only concepts a user sees, names, or configures.** Internal abstractions with
no user-facing presence (Environments, the task primitive, services, the streaming protocol) are not
here — they live in §5 and §10.

**Project (aka Repo).** A connected git repository — "Project" and "Repo" are the same thing; a
project *is* the repo you pointed Sculptor at. It is the parent of its workspaces and carries
repo-level settings the user can configure: a default system prompt, an optional workspace **setup
command**, and a branch-naming pattern.

**Workspace.** An isolated copy of a project's repository where agents do their work, so they never
edit your own checkout directly. By default a workspace is a **git worktree** — it shares your repo's
history but has its own branch, so the agent's commits land in your repo immediately and you can push
them yourself. This is the standard mode in both the GUI and `sculpt run`. Two other modes exist as
**experimental** opt-ins (→ §7.12): a full **clone** (a separate clone whose remotes mirror your
repo's, where the agent's commits stay in the clone until you push the branch back — to a remote you
share with your local repo, or directly to your on-disk repo) and **in-place** (the agent
works directly in your checkout, with no isolation). A
workspace's mode is fixed for its lifetime.

A workspace also has a source branch, a **target branch** (what its changes and any PR are measured
against), a **setup status** (if the project defines a setup command), and a set of **changes** that
may still be computing just after the agent edits files. It is shown as a tab.

**Agent.** One LLM conversation bound to a workspace — the user-facing unit of work, shown as a tab
inside the workspace. An agent has a **status** the user sees as status dots and tab state:
*building* (it's being set up), *running* (actively working), *ready* (idle / done), *waiting* (it
asked a question or wants plan approval), *error*, or *request-error* (its last request failed but
the agent is still usable). Several agents can run in one workspace; they share its files and git
state but each keeps its own conversation and history.

**Task (internal, not a product concept).** An agent is internally backed by a general-purpose
**task** primitive, vestigial — the only non-agent task types are test-only. A user
never sees or names a "task"; it survives only as a storage and scheduling detail behind an agent.
Its internal status, and an agent's TODO-item statuses, are each distinct from the user-visible agent
status above — don't conflate them.

**Message.** A single unit of conversation within an agent — from the **user**, the **agent**, or
the **system** (Sculptor itself, e.g. status and context notices). Messages appear incrementally as
the agent works. Plans and questions are their own message types; tool calls and errors appear as
blocks *within* a message rather than as messages of their own.

**Change / Diff.** A workspace's modifications measured against its target branch — the basis of the
Changes view (§7.5). Just after the agent edits files, the diff may briefly show as still computing.

**Commit / Branch / Pull Request.** The git outputs of a workspace. A workspace owns a branch; the
agent or user makes commits on it; and a workspace can open a **pull request** against its target
branch, after which Sculptor tracks the PR's CI and review status (and can "babysit" CI → §7.6).

**Skill.** An invocable, named workflow — bundled (the spec → architect → plan → build → review
pipeline, plus `fix-bug`, `mock`, and `setup-repo`) or experimental (`handoff`, `stack`). Skills are invoked as
slash commands and typically run as their own agent. (§7.8.)

**Action / Note.** Workspace-scoped helpers around the conversation: **actions** are saved,
re-runnable prompts (organized into groups); **notes** are scratch text the user can fold into a
prompt. (§7.11.)

**Notification.** A surfaced system or agent event (e.g. an agent finished, or needs attention).

## 7. The Product, Feature by Feature

This is the body of the spec — each feature described in prose: what it is, how it behaves, and its
notable edge cases. The sections follow the product's own `docs/help/` decomposition.

### 7.1 Onboarding & connecting a repo

The first time you open Sculptor, a short **setup wizard** walks you through three steps — your
details, dependencies, and connecting a repo — with a row of dots at the bottom tracking your
progress. You can jump back to an earlier step at any time; steps you haven't reached yet stay locked
until you get there. If you quit partway through, reopening Sculptor returns you to the first step you
haven't finished.

The first step collects your **details**. Enter your name and email and click **Get Started** to
create an account (the button stays disabled until you've entered a valid-looking email address, i.e.
one containing an `@`). If you'd rather
not sign up, **Continue without an account** skips straight ahead. This step is also where you make
your **telemetry** choice — a checkbox (on by default) governs whether Sculptor shares crash reports
and usage data — alongside an optional marketing opt-in and a reminder that your code stays yours:
Imbue does not store your repositories or train on your code. Your account email later lives under
**Settings › Privacy**.

Next, Sculptor checks the **dependencies** it needs — chiefly the Claude CLI and Git. Each shows up
as a card: a green check with the detected path and version when it's ready, or a warning with an
**Install** or **Sign in** button when it isn't. Sculptor can install and manage Claude for you
(showing live install progress) or sign you in, and for anything you'd rather manage yourself you can
expand a card to override the binary path or switch between a managed install and your system one. The
sign-in flow also supports a **paste-a-code** path for headless or remote setups where a browser
callback can't reach the app: Sculptor shows the sign-in URL, you approve access, and paste the
returned authorization code back into the card to finish signing in. A
**check again** link re-runs the checks. You can't move on until everything required is satisfied.

Finally, you connect your first **repository** (→ §7.2 Workspaces). Point Sculptor at a repo by
typing its path or, on desktop, browsing for a folder, then click **Add**. If the folder isn't a Git
repo yet, or is a repo with no commits, Sculptor offers to initialize it or make an initial commit
for you; a bad path surfaces an error you can dismiss. Once a valid repo is connected the wizard
finishes and drops you into the app, ready to create a workspace and prompt your first agent.

### 7.2 Workspaces

A **workspace** is how you start work in Sculptor: you pick a project (repo) and Sculptor creates an
isolated copy of it for agents to work in, rather than touching your own checkout. You create one
from the **Add Workspace** form (titled "Name your workspace") — choosing the repo, the source branch
to start from, a workspace name, the name for the workspace's new branch (with a live preview and a
warning if that branch already exists), and the **type of the first agent** to create (Claude, a
terminal agent, Pi where enabled, or a registered agent → §7.4). By default
the workspace is a **worktree**: it shares your repo's history but gets its own branch, so the
agent's commits show up in your repo right away and you can push them yourself. (The older **clone**
mode and the unisolated **in-place** mode are experimental opt-ins that, once enabled in Settings,
add a mode picker to this form — see §7.12.) Each open workspace is a **tab**.

Inside a workspace, a header **banner** shows where you are: the repo, the workspace's branch (which
you can copy), and a one-glance **diff summary**. The banner also shows the workspace's **target
branch** — what its changes are diffed against — with a selector to change it and a warning if an
open PR's target wouldn't match. The selector works for **every repo regardless of remote host**; a
repo with a remote offers its remote-tracking branches as targets, while a repo with no remote falls
back to offering the repo's own local branches. (Opening a pull request, by contrast, requires
a GitHub or GitLab `origin` → §7.6 — the target-branch concept is independent of the PR surface.)
A non-default mode (clone or in-place) is shown as a strategy badge, and the banner collapses
progressively as space tightens.

If the project defines a **setup command**, it runs when the workspace is created; its progress and
logs are surfaced, with controls to cancel or re-run, and the workspace's diff isn't meaningful
until setup finishes.

A workspace can hold **multiple agents**, shown as tabs within it. They all share the same files and
git state — there is no locking between them, so two agents editing the same workspace can step on
each other — but each has its own conversation, status, and history. You can add, rename
(double-click), reorder, mark-unread, and delete agents, and a small **peek** popover previews other
agents' state on hover.

Deleting a workspace removes it and all of its agents; for worktree and clone workspaces this also
cleans up the underlying git worktree or clone. A workspace whose underlying repo or working copy
has gone away surfaces an error state rather than failing silently. _(→ Changes §7.5, Agents §7.4,
Pull Requests §7.6; isolation guarantees §9.1.)_

### 7.3 Chat & terminal agents

An agent's main panel is one of two surfaces: the **chat** interface most agents use, or a full-pane
**terminal** that you drive yourself. This subsection covers both — running and coordinating *several*
agents at once is §7.4.

#### 7.3.1 Rich chat agents — the core agent loop

**Chat** is where you direct an agent. You compose a prompt in the input box at the bottom, and the
agent's reply, its tool calls, and its progress stream into the panel above. Press the send
keybinding (or click **Send**) to send; the editor and any attachments clear. The Send button
explains itself when it can't act — for example when the editor is empty. The send keybinding is
**Cmd/Ctrl+Enter**, so a plain **Enter** (or **Shift+Enter**) inserts a line break and a prompt can
span several lines while still sending as one message.

The input toolbar shapes how the agent handles your next message. A **model** picker chooses which
model answers — present only for agents whose harness supports model selection (a Claude or Pi chat
agent), and shown disabled with the current model for those that don't; the list it offers comes from
the agent's own harness, so a **Claude** agent picks from the Claude models while a **Pi** agent
surfaces Pi's live catalog grouped by provider, and changing a Pi agent's model takes effect in-session
(a failed switch leaves the choice unchanged and raises an actionable error toast). An **effort**
selector budgets how much thinking it spends per step (Low, Medium, High, Extra High, Max — Extra High
by default); a **fast mode** toggle trades some depth for quicker output on the models that support it
(the Opus family, including Opus 4.8) and is disabled for the rest; and **plan mode** makes the agent
investigate and propose a plan for your approval before it changes anything. The **+** button opens a
menu for adding context — point the agent at specific **files and folders**, attach **images** (you
can also drag-and-drop or paste them), or start a **skill** (→ §7.8 Skills); with the **Entity
Mentions** experimental toggle on (→ §7.12) the same menu also lets you reference **workspaces and
agents** and **repositories**. (The `+` menu is distinct from the inline triggers: typing `@` searches
files and folders — and those same entities when enabled — and `/` opens skills directly.) Attached
items show as small pills above the input, each removable with an **×**. Typing `/` opens
the command picker for conversation commands — `/clear` to reset the agent's context, `/copy` to copy
its last response, and `/btw` for a side question (below), alongside other built-ins like `/compact`,
`/context`, `/simplify`, `/batch`, and `/loop` — and for skills.

While the agent works, a **status indicator** above the input reports the live phase — Thinking…,
Streaming…, Calling tools…, Compacting…, Stopping… / Stopped, and "Waiting for background tasks…" — with a
running timer, and for multi-step work it
shows progress like "3 / 8 · current step"; hover or click to expand the full checklist. You
steer mid-turn without waiting for it to finish: a **stop** button (Ctrl+C) interrupts the running
turn, you can **queue** a message to run after the current turn (it appears in a bar below the input,
where you can edit or remove it), or you can **interrupt-and-send** to cut the turn short and deliver
your new message immediately. Spawned **subagents** appear inline as pills showing their prompt and
elapsed time, expandable to reveal what they did (→ §7.4 Agents).

You can also ask a quick **side question** without derailing the turn. Typing **`/btw`** followed by
a question (e.g. `/btw why did you take this approach?`) opens a small, draggable popup in the corner
that streams a short, **read-only** answer based on the agent's current session — it doesn't post to
the conversation, change anything, or interrupt the agent's work, and asking another `/btw` replaces
the previous popup. Because it works from the agent's session, it's available only after you've sent
at least one message. The side question is answered by a fast model (Haiku) forked read-only from the
agent's **Claude** session, so it's a Claude-agent affordance: a terminal agent (which has no chat
input) doesn't offer it, and a **Pi** agent has no equivalent side channel (→ §7.4).

Sometimes the agent turns the question around and asks **you**. A **question panel** replaces the
chat input, showing the question, its options, and an **Other** choice for a free-text answer.
Questions can be single- or multi-select; when there are several you move between them with the
progress dots or Tab, and submitting jumps to the next unanswered one until every question is
answered and the panel closes. You can also **dismiss** the panel to decline. Answered questions
remain in the chat history as plain text for the record.

When a turn finishes, a **footer** summarizes it: duration (with a "Stopped" label if you interrupted
it), token count, how much of the context window is in use, and a "N files changed" link that opens
the affected files. If a message fails to send or a turn errors out, Sculptor surfaces the error —
preserving your typed text so you can resend — and an errored agent offers a link to try to restore
it (unless its workspace was deleted, in which case it can't be recovered).

Beyond composing prompts, the chat offers a few conveniences for working in a long conversation:
recall earlier prompts by pressing the up/down arrows in an empty input, search the transcript
(Cmd/Ctrl+Shift+F), and switch tool calls between compact pills and expanded rows
(Cmd/Ctrl+Shift+E). Right-clicking an image anywhere in the conversation (a message, the attachment
preview, or the zoomed lightbox) offers **Copy Image** to put it on your clipboard.

#### 7.3.2 Terminal agents

Not every agent is a chat agent. A **terminal agent** is an agent type whose main panel is an
interactive, full-pane terminal — a real shell session (a PTY) running inside the workspace — rather
than a chat transcript. You type into the
shell directly; Sculptor renders no message stream, model picker, or chat input for it, so the
chat-only affordances above (plan mode, queued messages, `/btw`) don't apply. It is still a
first-class agent — its own tab, name, status dot, history, and lifecycle, sharing the workspace's
files and git state with its siblings (→ §7.4). The reason to use one is to run a coding tool that
drives *its own* terminal UI — most importantly a CLI coding agent like Claude Code — alongside your
chat agents, while Sculptor still tracks it as an agent and surfaces its edits in the Changes view.

Terminal agents come in two flavors. A **plain Terminal** is just a bare login shell in the
workspace, for running whatever you like by hand. A **registered terminal agent** additionally
launches a specific command on start, and is defined by a small **registration**: one TOML file per
agent under the Sculptor folder's `terminal_agents/` directory, named by a `registration_id` (the
file's stem) and declaring a `display_name` (what the create menu shows), a `launch_command` to run
when the agent starts, an optional `resume_command_template` (so the agent can reattach to the same
underlying session after a Sculptor restart), and whether it `accepts_automated_prompts`. The
directory is re-read on demand, so dropping in a new file makes a new agent type available with no
restart; and the launch parameters are stamped onto the agent when you create it, so it keeps working
even if you later edit or delete the registration file.

Sculptor ships one registration out of the box — **"Claude CLI"**, which runs the Claude Code
terminal UI in the workspace. It's installed automatically on first run into your `terminal_agents/`
folder, where it's yours to edit or delete (deleting it sticks — Sculptor won't reinstall it). It
launches Sculptor's managed Claude binary with the bundled Sculptor plugins loaded, and a companion
hooks file wires the CLI back into Sculptor: as the agent works, the hooks call the **`sculpt signal`**
CLI (→ §8) to report **busy / idle / waiting** status — lighting the same status dots a chat agent
uses — and **files-changed** to refresh the Changes diff, and to hand back the session id Sculptor
needs to resume the conversation later.

This is the key distinction from the rich **Claude** chat agent described above: both run Claude, but
the chat agent is driven *through Sculptor's own chat surface* (Sculptor renders its messages, tool
calls, plans, and questions), whereas the "Claude CLI" terminal agent **is** the Claude Code TUI
itself, drawn in a PTY, with Sculptor observing it from the outside via signals. You choose which
kind of agent — a Claude or Pi chat agent, a plain Terminal, or a registered terminal agent — when
you create it (→ §7.4 Agents).

### 7.4 Agents — multiple roles & background

A workspace can hold several **agents** at once, each its own conversation with its own history and
pending changes, shown as a row of **tabs**. Each tab carries the agent's name and a **status dot**,
and hovering the dot tells you the status and how long since its last activity. Click a tab (or use
the next/previous-agent keybinding) to switch between them.

Create a new agent with the **+** button at the end of the tab bar (or the new-agent keybinding); it
creates an agent of your last-used **type**. Next to it, a small **chevron** opens a menu of the types
you can create: the built-in **Claude** rich-chat agent (and the experimental **Pi** chat agent where
enabled → §7.12), a plain **Terminal**, and then each **registered terminal agent** by its display
name — out of the box that's **"Claude CLI"**, which runs the Claude Code TUI in the workspace (→ §7.3
Chat). The menu marks your last-used type with a check, Sculptor remembers it, and a plain **+** click
re-creates that type without opening the menu. **Double-click** a tab to rename it (Enter saves, Escape cancels), drag tabs to **reorder**
them, and right-click for more: rename, **mark as unread**, **copy the agent's name**, delete, plus
diagnostics. **Deleting** an
agent (after confirming) moves you to the next one, or starts a fresh agent if it was the last.

Because every agent in a workspace works on the same copy of your repo, **siblings share its files
and Git state with no locking**. In practice it's rare to have two of them *actively editing* at the
same moment — and you wouldn't want to, since with no lock to stop them, two agents touching the same
file at once can step on each other. The real reason to keep several agents in one workspace is to
hold **separate contexts and roles** over the same code: an *implementer* agent and a *reviewer*
agent, say, or one agent carrying the main feature work while another is a scratch context for a side
investigation or a quick experiment — each with its own conversation and history, all looking at the
same files. When you do want genuinely *simultaneous* work, divide it across different parts of the
codebase or stagger dependent tasks so the agents don't collide — though for fully independent,
parallel work, separate **workspaces** are usually the better tool (→ §7.2, scenarios S2/S5). Beyond
your siblings, a single agent can spin up its own **subagents** to fan out sub-tasks, and can run
longer **background tasks** that keep going while you read its main reply (→ §7.3 Chat).

To check on a workspace without leaving the one you're in, hover a workspace tab to open a **peek**
popover: a quick preview of that workspace's status, its list of agents, branch, pull-request state,
and diff stats. Moving between tabs swaps the preview instantly; for a busy workspace it shows the
first few agents with a "+N more" control to reveal the rest. Click an agent row (or the header) to
jump straight there.

### 7.5 Changes — review & commit

When an agent edits files, you review the result in the **Files** panel, which sits at the top-left
of the workspace and carries three tabs: **Browse** (the workspace's full file tree, for opening any
file), **Changes** (every modified file), and **Commits** (the workspace's commit history). The
Changes and Commits tabs show a count badge when there's something to see. Nothing leaves the
workspace until you choose to commit (→ §7.6 Pull Requests).

The file tree can be shown as a nested **tree** or a flat list, and you can toggle between them,
collapse every folder at once, or refresh to re-fetch. A search control filters the tree as you type
— ancestor folders of matches expand automatically, and "No matches" appears when nothing fits. In the
**Changes** view each file carries a status letter (modified, added, deleted, renamed) in a distinct
color along with its added/removed line counts; folders roll those up into a change-count badge,
deletions are struck through, and a file that failed to process shows an error badge. (The **Browse**
tree lists the whole repository without these change decorations.) When the agent is actively touching
a file, the tree scrolls to it, opens its ancestors, and briefly **highlights** the row so you can
follow the work as it happens. Right-clicking a file or folder opens a menu with actions like opening
its diff, viewing the file, and copying its path (full or relative) — plus, when Sculptor can reach
your local filesystem, opening it in your OS's default app and revealing its containing folder.

Clicking a file in the **Changes** tab opens it in the main **diff** view; clicking a file in
**Browse** opens its read-only contents instead, since an unchanged file has no diff. A scope picker lets you look at only the
**uncommitted** changes or, when the workspace has a target branch (any repo → §7.2),
**all** changes measured against that target branch, with a count on each option. The diff itself can be shown **side-by-side** or **unified** (inline), with line-wrapping, a
find-in-file search that highlights matches and counts them ("X of Y") as you step through, and an
expand control that widens the diff across the whole window. A binary file replaces the diff with an
explanatory banner, and renamed or deleted files show a banner above the diff — and for images, a
before/after preview with zoom and pan — while a very large diff is truncated behind a "Show full diff" button. When the
experimental **Rich markdown rendering** feature is enabled (→ §7.12), a markdown file can be flipped
between its raw source and a rendered preview. You
can also open a file's full read-only contents with syntax highlighting rather than a diff, and — with
the experimental **Review All** feature enabled (→ §7.12) — a
"Review All" option gathers every change into a single combined diff tab. In the **uncommitted** scope, each changed file has a
**Discard changes** action that reverts just that file to its last committed state after you confirm.

When you're satisfied, the **Commit** button at the top of the Changes tab, above the file list — labeled with the
pending count, e.g. "Commit 2 changes," and disabled when there's nothing to commit — asks the agent
to write a message and make the commit on the workspace branch. Committing does not push; the commit
stays on the branch until you push it or open a PR/MR. Clicking the button does a **quick commit**
with the default prompt; right-clicking it opens a dialog to **edit and save the commit-message
prompt**, which then steers how messages are written on subsequent commits.

The **Commits** tab shows the workspace's history as a **commit graph** with connecting dots and
lines. Each entry shows the first line of its message, the file count, added/removed stats, a
relative time, and a short hash; hovering reveals a popover with the commit's author, date,
and short hash, and a copy button that copies the full hash, confirming by briefly swapping its icon for a checkmark. Clicking an entry expands it to
list the files in that commit, and clicking one of those files opens a diff of that file against its
parent. Merge commits can be expanded to follow the merged-in branch, and a marker at the bottom
shows where the workspace's history forks from its starting point.

### 7.6 Pull Requests

The pull-request surface described here appears **only when the workspace's repo has a GitHub or
GitLab `origin`**; for any other repo there is no PR/MR control and you push the branch yourself. (The
target-branch selector itself is *not* gated this way — it appears on every repo, → §7.2; only opening
a PR/MR requires a detected provider.) Given such a repo, once you've committed work on a workspace branch you can
open a **pull request** (on GitHub) or **merge request** (on GitLab) straight from the workspace's
top bar — Sculptor stays provider-neutral, so the control reads "Create PR" or "Create MR" to match
your repo. Clicking it pushes the branch and
asks the agent to open the request against the workspace's target branch. If you'd rather adjust how
that's done first, the button's chevron menu offers **Edit prompt...**, which opens a dialog to revise
the PR/MR-creation prompt before you create anything. While Sculptor is looking up status, the button
shows a spinner with "Checking PR..."/"Checking MR...".

Once a request exists, the button displays "PR #N"/"MR !N" alongside small status dots for its
**pipeline/CI** and **review** state; hovering the dots explains them ("Pipeline running/passed/
failed," "Approved/Review pending," and so on). Clicking the number opens the request in your browser.
The chevron opens a **detail dropdown** with the title and link, checks/pipeline status, approvals and
reviewer names, and any unresolved comments. If a **CI babysitter** is available, a switch in this
dropdown lets you pause or resume it — when on, Sculptor keeps an eye on the request's CI for you —
and the status text updates as you toggle it. When the babysitter *can't* run — for example its
configured agent type can't be resolved for this workspace — the dropdown surfaces a short
**disabled reason** in place of the usual status, and for a persistent reason the switch itself is
forced off and greyed out until the cause is fixed.

When the request is **merged** or **closed**, the button switches to a merge icon reading "PR #N
merged"/"closed," and clicking it still opens the request in the browser. If a request already exists
but targets a different branch than the workspace does, the button becomes **Assign PR/MR**, offering
to create a fresh request against the workspace's target or to switch the workspace's target to match
the existing request. The target-branch selector itself flags the mismatch in a warning color, with a
hover hint like "PR #N targets {branch} — retarget?". (A failing CI check itself just shows a red
pipeline dot / "Failed" badge on the normal button.) If Sculptor can't *look up* the request's status
at all — the provider CLI is missing, you're not authenticated, the host is rate-limiting, and so on
— the button turns into an error state: a warning triangle for something you can act on, or an info
icon otherwise, whose popover gives a title, description, optional details, and sometimes a copyable
remediation command.

### 7.7 Terminal

Sculptor includes a built-in **workspace terminal** — a real shell that runs inside the current
workspace, so anything you type operates on the very files the agent is working with. It's handy for
starting a dev server, running tests or linters, inspecting git state, or any command that's quicker
to run yourself than to ask the agent for. You open it from the command palette or the panel controls
in the bottom bar, and it can sit open alongside a running agent without interfering with the
conversation.

You can keep several terminals going at once. The **+** in the tab bar adds another ("Terminal N"),
double-clicking a tab renames it inline, and each tab is an independent shell in the same workspace;
right-clicking offers rename, close, and "Close others," tabs can be reordered, and closing the last
one spins up a fresh replacement. When output arrives in a tab you're not looking at, a pulsing
**unread** dot appears on it and clears when you switch over. A starting terminal briefly shows
"Starting terminal..." while it
comes up; Ctrl+L clears the focused terminal; and your terminals — along with their scrollback —
persist as you navigate around Sculptor rather than resetting each time.

This section is about your own terminal. It is distinct from a **terminal agent** — an agent type
whose main panel is a shell the *agent* drives rather than you (→ §7.3 Chat, §7.4 Agents).

### 7.8 Skills & Workflows

A **skill** is a reusable agent capability you invoke as a slash command from any chat input — type
`/` to open the picker (which also lists built-in conversation commands like `/clear` and `/compact`
alongside skills → §7.3). Skills run as full agents with their own tools, so they can read your
codebase, spawn parallel subagents, and adapt to your repo. Sculptor surfaces three kinds: the
**built-in** skills it ships with, the **Sculptor** plugin skills (the workflow and experimental sets
below, plus the base `sculptor` plugin's `help` and `sculpt-cli`), and any **custom** skills you've
installed under your home or repo `.claude/` directory. They all appear together in the picker, sorted
alphabetically.

The dedicated **skill library** panel lists every available skill grouped by type under collapsible
headers. Hovering a skill opens a popover with its
description; moving to another skill swaps the content instantly. Clicking a skill drops
`/skill-name` into the chat input, ready to send (and a custom or Sculptor skill's chip carries an
**Open in Sculptor** control that opens the skill's file in a viewer tab so you can read its definition). The
panel has its own search box that filters as you type, with arrow-key navigation and a type filter to
narrow which kinds are shown. While the agent is running, the chips are disabled; the panel also has
clear loading, empty, and error states.

The flagship bundled skills form the **engineering workflow** (the `sculptor-workflow` plugin): a
pipeline that takes a feature from idea to shipped code in focused stages — **spec → mock → architect
→ plan → build → review**. Each stage is its own skill and runs as its own dedicated agent, renamed
to match the stage ("Spec", "Architect", "Plan", and so on) so you can tell the tabs apart, and each
produces a durable artifact on disk that the next stage reads. `spec` writes the implementation spec
through guided Q&A you watch take shape in the diff viewer; `mock` produces interactive HTML mocks
(exploration mode generates several variants to compare, confirmation mode refines one); `architect`
writes the architecture document; `plan` turns it into a folder of self-contained task files; `build`
executes them one at a time, committing as it goes; and `review` checks the diff against the spec,
re-runs the tests, and writes up its findings. You don't have to run the whole pipeline — every stage
takes a feature *slug*, finds the earlier artifacts, and offers to **hand off** to the next stage
when it finishes.

Two more workflow skills stand alone. **`setup-repo`** is run once per repo to create the small
config files that teach the other skills how your codebase builds, tests, and where it keeps docs
(other stages invoke it for you if those configs are missing). **`fix-bug`** is a self-contained,
test-driven bug fix: it reproduces the bug with a failing test, fixes the code, and verifies —
interactively by default, or end-to-end with no questions when run autonomously, optionally opening a
pull request if the repo allows it.

### 7.9 Command Palette & Navigation

Sculptor is organized into **tabs** along the top: a **Home** tab, a **Settings** tab, and a tab for
each open workspace. You switch tabs by clicking, cycle through them with keyboard shortcuts (these
keep working even in zen mode), drag to reorder them, and close them with the tab's minimize button, a middle-click,
or a keyboard shortcut. Workspace tab labels truncate when long and carry a small **status dot**
reflecting the agent's state; double-clicking a tab renames the workspace inline, and right-clicking
opens a context menu to rename it, delete it, copy its name / branch / workspace id, or close
others/all. **Cmd+Shift+W** deletes the active workspace (after the same confirmation dialog as the
menu and palette actions). When too many tabs are open they overflow into a horizontal
scroller that keeps the active tab in view, and closed workspaces collect into a pill you can reopen
from. Tabs persist across restarts.

The **Command Palette**, opened with **Cmd+K** from anywhere, is the fastest way to get around once
you have several workspaces and agents open. It's a searchable list with the input focused and
commands grouped (Workspaces, Navigation, Theme & Layout, Chat, Terminal, Help). Type to filter
(fuzzy and case-insensitive, with groups reordering by best match), move with the arrow keys, press
**Enter** to run a command — or **Cmd+Enter** to run it and keep the palette open for another. Some
commands open **sub-pages** (shown with a chevron and reached with Tab) such as the workspace
switcher, which **Cmd+P** opens directly. From the palette you can switch between or create workspaces
and agents, show or hide panels, open Settings or Help, and toggle the theme. Commands
that don't apply right now are greyed out with a reason ("Only one agent in this workspace", "No
uncommitted changes"), and rows show their keyboard shortcut where one exists.

The **bottom bar** carries toggle buttons for the left, bottom, and right side panels plus a
focus-mode button. Clicking a toggle shows or hides that panel and updates its active state; a panel
with no content is disabled with a "Panel is empty" tooltip; and hovering any toggle shows its name
and keybinding. **Focus mode** (Cmd+\) collapses all side panels so the chat expands, and toggles
back. **Zen mode** (Cmd+Shift+\) goes further, hiding the top bar and side panels entirely to leave
just the chat with a draggable title bar; an "Exit zen mode" button appears when you move to the
top-left corner. The app's **version number** sits in the bottom-right — in the workspace bottom bar
and in the corner of the non-workspace pages; clicking it opens a popover with version details,
update status, and diagnostics, and a colored dot plus toasts signal when an update is downloading or
ready to install. A **Report a problem** button sits alongside the version indicator for sending
feedback.

### 7.10 Settings

**Settings** (opened with Cmd+, or from the top bar) is a single page with a sidebar of sections; it
remembers the last section you viewed and can be deep-linked to a specific one. Changing a setting
saves on the spot with a "Setting updated" toast (or an error toast on failure).

The **General** section controls appearance — the Light / Dark / System theme — and software updates,
including the release channel and a "Check for updates" / "Install and restart" control. **Agent**
sets the defaults applied to new agents: the default model, fast mode, and effort level.
**Keybindings** lets you search, view, assign, clear, and reset every keyboard shortcut, warning you
when a combination conflicts with an existing one. **Panels** governs the default panel layout —
which zone each panel lives in, per-panel hotkeys, and which non-builtin panels are enabled — with a
reset-to-defaults. **File Browser** sets diff defaults (split versus unified, line wrapping, the
default split ratio), tab-close behavior, and the commit-message prompt.

The repo-facing sections are **Repositories**, **Git**, and **CI**. Repositories lists your connected
repos with their paths and agent counts and lets you add or remove them and configure each one's
**setup command** and **branch-naming pattern**. Git holds the cross-repo defaults: the pull-request
creation prompt, PR-status polling and its interval (plus a multiplier that throttles polling for
closed workspaces), the default target branch, the global
branch-naming pattern, and the branch-deletion policy. CI configures the **CI babysitter** that
watches pipelines and asks an agent to fix failures — a toggle, a retry cap, a **babysitter-agent
selector** (which agent type the babysitter drives: the workspace's most-recently-used agent by
default, or a pinned Claude, Pi, or registered terminal agent that accepts automated prompts), and
editable prompts for pipeline failures and merge conflicts.

The remaining sections cover the environment and account. **Dependencies** manages the Claude CLI and
git binaries Sculptor uses — switching between a managed install and a custom path, showing each one's
version and health. **Pi (experimental)** is the parallel dependency manager for the experimental Pi
agent harness — its binary (managed or custom path), version, and the API-key environment variable it
needs. **Environment Variables** surfaces the global and per-repo `.sculptor/.env` files (which you edit
directly) and controls whether they override existing variables. **Privacy** shows your (read-only) email address and
the telemetry opt-out. **Actions** is the full manager for your saved prompts and groups, including
import/export (→ §7.11). **Experimental** holds opt-in feature toggles and the custom backend command
(→ §7.12). A **Theme Builder** section lets you fine-tune fonts, the code theme, accent and semantic
colors, border radius, UI scaling, and panel translucency, with a component gallery and a reset.

### 7.11 Actions & Notes

**Actions** are saved, re-runnable prompts that live in a workspace panel as one-click chips,
organized into **action groups** (the built-in "Sculptor" group — which ships `/help` and `/fix-bug`
shortcuts — sits first, with any ungrouped actions at the bottom; collapsed group headers carry a count badge). Clicking an action either sends
its prompt immediately (an auto-submit action, shown with a play icon) or appends it to the chat input
for you to edit first (a draft action, shown with a text-cursor icon); a hover tooltip previews the
prompt. For a **terminal agent** — which has no chat input — a draft action instead types its prompt
into the agent's terminal (the PTY) *without* pressing Enter, so you can edit and run it yourself,
while an auto-submit action types and submits it. While the agent is running, a right-click **Queue message** option on an action lets you queue
its prompt to run after the current turn rather than sending it immediately. You create, edit, and delete actions through a dialog (Name, Prompt, Group, and an
auto-submit toggle), manage groups inline (add, rename, delete), and drag actions and groups to
reorder them or move an action between groups — built-in items can't be edited, deleted, or dragged.
The same actions can be managed in bulk from Settings, including import and export to a JSON file
(→ §7.10).

**Notes** are a per-workspace scratchpad: a panel of free-form text you can type into, which persists
as you switch away and back. When you're ready, **Add notes to prompt** folds the note text into the
chat input (if the input already has content, it asks whether to overwrite), and a copy button copies
the note out; both controls disable when there's nothing to act on.

These helpers sit alongside the chat input's **mentions** and **path-autocomplete**. Typing `+` opens
a category picker (Files & folders, Skills, Workspaces and Agents, Repositories, and Images where
supported), `@` searches files and folders, and `/` searches skills — each inserting a **mention chip** into the
prompt. In path fields (such as adding a repo), typing a path beginning with `/` or `~` brings up a
directory autocomplete you can drill through before submitting.

### 7.12 Experimental & in-development features

Sculptor gathers its in-development capabilities under one banner — **Settings → Experimental**,
described there as "Features that are still being developed. These may change or be removed." The
product makes no finer distinction than that: a feature is either generally available or
**experimental** (opt-in). The experimental surface as it stands today:

**Experimental feature toggles** (Settings → Experimental), most an opt-in switch:
- **Clone workspaces** and **In-place workspaces** — worktree is the only workspace mode out of the
  box; enabling these adds the older **clone** mode (a full git clone whose remotes mirror your
  repo's, where commits stay in the clone until you push the branch back to your repo) and the
  unisolated **in-place** mode to the Add Workspace picker (→ §6, §7.2).
- **Always interrupt and send** — a new message immediately interrupts the running agent instead of
  being queued (→ §7.3).
- **Smooth streaming** — animate streamed text smoothly rather than showing it in bursts. (Unlike the
  other toggles here, this one is **on by default**.)
- **Per-workspace panel layout** — panel visibility and sizes become local to each workspace (panel
  positions stay shared).
- **Review All** — adds the combined "Review all changes" diff view to the Files panel (→ §7.5).
- **Entity Mentions** — type `+` in the chat input to mention repositories, workspaces, and agents
  (→ §7.11).
- **Rich markdown rendering** — render `.md` / `.markdown` files as formatted HTML in the file
  viewer, toggled by the eye icon in the diff toolbar.
- **Pi agent** — offer the experimental **Pi** agent as a choice when creating an agent (→ §7.4); an
  already-running Pi agent keeps going regardless of the toggle.
- **Frontend plugins** — enable the experimental plugin system that lets third-party plugins extend
  Sculptor's own UI (the plugin system below). Off by default; turning it off only fully takes effect
  after an app reload, since already-loaded plugins aren't torn down live.
- **Custom backend command** — the entry point for the container / remote backend described below.

The **CI babysitter** (→ §7.6, §7.10) is likewise experimental and off by default.

**Experimental skills** (the `sculptor-experimental` plugin, invoked as slash commands, → §7.8):
- **`handoff`** — hands the current work to a fresh agent seeded with a summary of where you are,
  either as a new agent in the same workspace (sharing the branch and uncommitted files) or a
  brand-new workspace on its own branch cut from the current one.
- **`stack`** — a handoff into a new workspace whose branch is both based off and targets the current
  branch, scoping the new workspace's diff and any pull request to just the work stacked on top.
  Available only from worktree workspaces.

**Experimental panels.** Optional, non-builtin panels can be enabled from Settings → Panels — most
notably the in-app **Browser** panel (desktop-only), which embeds a browser beside the chat with an
address bar and back/forward/reload/screenshot controls; outside the desktop app it shows a
placeholder.

**Frontend plugin system.** With **Frontend plugins** enabled, Sculptor can load third-party
**plugins** that extend the app's own UI from inside the renderer — contributing new **panels** (which
show up in the Panels list with a "plugin" badge) and full-screen **overlays**, built against a small
versioned Sculptor SDK that reuses the host's React, Radix theming, icons, and shared data client so
they look and behave like native UI. A new **Plugins** section appears in Settings to manage plugin
**sources**: you add a plugin by dropping its folder into the Sculptor folder's `plugins/` directory
(picked up on the next launch or via a **Refresh** button) or by adding the **URL** of a plugin
server (saved and re-fetched on every launch). Each row has an enable/disable switch (mute a plugin
without removing it) and, while enabled, Settings and Reload controls; user-added URL sources can also
be removed, while bundled and disk-discovered plugins can't. Sculptor ships a bundled **Linear** example
plugin and two no-build example plugins (**Sculpty** and **Pomodoro**). Because a plugin runs with the
**same privileges as Sculptor's own UI** — and a URL source serves whatever code it holds at load time
— adding a plugin means running that code, so you should only add sources you trust (the plugin trust
model is documented in `SECURITY.md`; outbound links a plugin opens are restricted to `http(s)`).

**Container / remote execution backend.** Pointing the **custom backend command** at a launcher lets
Sculptor run agents somewhere other than your host machine — inside a Docker container, on a remote
server over SSH, or in a VM. The launcher starts the backend and prints a URL the app connects to;
the GUI, workspace management, and agent orchestration are otherwise unchanged. A companion
**backend-readiness timeout** sets how long the app waits for that URL to come up, and the app
automatically restarts the custom backend (with backoff) if it crashes. The command can be set either
in Settings or through an environment variable, and setting or clearing it requires restarting the app
(→ §9.1 for the isolation and trust implications).

## 8. The `sculpt` CLI  _(core product surface)_

`sculpt` is a first-class way to drive Sculptor **headlessly** — from a terminal, a shell script, or
CI — against the very same local Sculptor that the desktop app talks to. Anything you create with
`sculpt` shows up in the GUI, and anything you create in the GUI is visible to `sculpt`: a
**Workspace** you spin up on the command line opens as a real workspace in the app, and an **Agent**
you start from a script streams its conversation into the same chat panel a person would watch. This
makes `sculpt` the natural surface for automating Sculptor, scripting fleets of parallel agents, or
wiring coding agents into a pipeline.

The CLI is organized into a handful of command groups, each mapping to a domain noun or a job:

| Group | What it's for |
|---|---|
| `sculpt repo` | List and show the **Projects (Repos)** Sculptor knows about — their paths and whether they're accessible. |
| `sculpt workspace` | Create, list, show, rename, and delete **Workspaces**. Pick the isolation **strategy** (`--strategy`: `worktree`, `clone`, `in-place`); choose the source branch (`--branch`), a name for the workspace's new branch (`--branch-name`), its target (`--target-branch`), and a description (`--name`) at create time; `list` can span all repos (`--all`) or one (`--repo`), and `delete` takes `--yes`/`-y` to skip the prompt. |
| `sculpt agent` | Manage **Agents** in a workspace: `create` one (with an opening `--prompt`, a `--model`, a `--name`, and a `--harness`), list (filter by status, scope with `--all` / `--repo` / `--workspace`), show, `send` a message (with `--model` and repeatable `--file` attachments), check `status`, read `messages` (`--limit`/`--tail`), `interrupt` a running one, rename, and delete. `send`, `status`, and `messages` all accept `--follow` to stream live. Choose the **model** (`haiku`, `sonnet`, `opus`, `fable`, plus the `sonnet[1m]` / `opus[1m]` 1M-context variants) and the **harness** (`--harness`: `Claude`, `Pi`, `Terminal`, or a registered terminal agent by display name; omitting it uses your most-recently-used type — the same default the GUI's **+** button applies, and an explicit choice updates that MRU). |
| `sculpt run` | One-shot convenience: from a single prompt, create a workspace **and** an agent in one step, optionally `--follow` its output live. Accepts the same workspace-creation flags as `sculpt workspace create` (`--strategy`, `--branch`, `--target-branch`, …) plus `--model`, `--file`, and `--harness`. Because `run` always sends a prompt, a terminal/registered harness is rejected here (use `sculpt agent create` for those). |
| `sculpt signal` | Run from **inside an agent's environment** to report state back to Sculptor — `busy`, `idle`, `waiting`, `files-changed` (refreshes the diff), or `session-id <id>` (which takes the session identifier as an argument). Lets terminal-based agents light up the same status indicators the GUI shows. |
| `sculpt ui` | Let an agent **drive the app's UI** for the user: `open-file` (open a file or diff tab, with `--mode auto`/`diff`/`file`) and `webview-navigate` / `webview-refresh` (point or reload the in-app Browser panel, e.g. at a generated HTML report). |
| `sculpt schema` | Print machine-readable **JSON Schemas** for command output (run with no argument to list the available schema names, including a dedicated `error` schema for `--json` failures), so scripts can validate and parse results reliably. |

Two conventions make the CLI script-friendly. Commands that emit results accept **`--json`** for
structured output (paired with `sculpt schema` for the exact shape) instead of human-readable text
(`sculpt schema` itself already prints JSON), and
**environment variables set sensible defaults** so you don't repeat IDs — most notably
`SCULPT_WORKSPACE_ID` and `SCULPT_AGENT_ID` (and `SCULPT_PROJECT_ID`, which the shell inside every
Sculptor workspace already sets); `SCULPT_API_PORT` (or a per-command `--base-url`) points the CLI at
a non-default local server. Workspace-scoped commands also take an explicit `--workspace`/`-w` flag
that overrides the env-var default, and the WebSocket-backed read commands (`agent show`, `status`,
`messages`) accept a `--timeout`. IDs can be given as short prefixes rather than full values.

A couple of example invocations:

```bash
# Kick off a fresh workspace + agent from a prompt and watch it work
sculpt run "Fix the failing auth tests" --repo ~/code/myapp --model sonnet --follow

# Drive an existing agent (workspace taken from $SCULPT_WORKSPACE_ID), as JSON
sculpt agent create --prompt "Add a /health endpoint" --model opus --json
sculpt agent send a1b2c3 "Also add a test for it" --follow

# From inside an agent's environment: surface a generated report to the user
sculpt ui webview-navigate file:///workspace/code/report.html
sculpt signal files-changed
```

## 9. Non-Functional Behavior

Beyond any single feature, Sculptor makes a set of cross-cutting promises about how it behaves — what
your agents can touch, how your work survives a crash, and what leaves your machine. These guarantees
hold across every workspace and agent.

#### 9.1 Isolation & safety

By default an agent works in an **isolated copy** of your repository, so it can read, edit, and run
real commands freely without ever touching your own checkout — the files you have open stay exactly as
you left them. Working **in place** in your actual checkout is the deliberate, opt-in exception. An
agent's edits are committed onto a **workspace branch** that belongs to that workspace; nothing is
ever pushed to a remote, and no pull request is opened, unless you take that action yourself. The
trust posture is straightforward: agents run real shell commands inside their workspace and can do
real work there, while you remain the gatekeeper for anything that reaches the outside world — pushes,
PRs, and merges back to your code. An **experimental container/remote option** goes a step further and
runs agents off your machine entirely (→ §7.12).

#### 9.2 Concurrency

You can run **many agents across many workspaces at once**, and they make progress in parallel without
getting in each other's way. The one thing to watch: agents placed in the **same** workspace share the
same files with no locking between them, so if you point two agents at overlapping work they can step
on each other's changes. Keeping concurrent agents on separate concerns (or separate workspaces) is
your responsibility (→ §7.4).

#### 9.3 Crash recovery & resumption

Quitting Sculptor — or having it crash — and reopening it **restores your workspaces, your agents, and
the full conversation history** right where you left them. An agent that was running is reattached and
resumed wherever that's possible, and a question an agent asked you before the interruption can still
be answered after you reopen the app. When something does go wrong, the app **surfaces the error**
rather than failing silently, and an agent left in an errored state can often be restored and
continued rather than lost.

#### 9.4 Responsiveness

The UI stays **live**: an agent's output, its changing status, and the file changes it makes appear in
real time as they happen, with no manual refresh. What you see stays consistent with what you clicked
— the app reflects the true current state of each agent and workspace rather than a stale snapshot.

#### 9.5 Persistence & durability

Your work is **stored locally and is durable**. Workspaces, agents, the complete conversation history,
and your settings are all saved on your own machine and survive both restarts and upgrades to a newer
version of the app — installing an update preserves everything you've done.

#### 9.6 Security & auth

Sculptor is **local-first and single-user**: it runs on your machine for you, and your code stays
there. Imbue does not store your repositories and does not train on your code. Credentials and keys the
app needs to do its work are handled locally on your behalf, and the boundary stays the same one
described in §9.1 — your code and secrets stay on your machine unless you explicitly send something
out.

#### 9.7 Telemetry & privacy

Anonymous usage telemetry is **opt-out**. You make the choice during onboarding, and you can change it
at any time in **Settings → Privacy**. When it's on, what's collected is high-level, anonymized
product-usage and error-reporting signal — which features are used and when things break. The
product-usage telemetry is designed to keep private content such as file names, branch names, and
prompts out of what is sent (for example, by masking captured page text); error reports are gated on
the same consent. Turning it
off is respected across restarts.

## 10. Testability & Engineering Substrate

The systems below are **not user-visible and not technically part of the product**, but Sculptor
cannot be built with high quality without them.

**Why this is a top-level concern:** Sculptor's correctness is mostly *emergent behavior* of
nondeterministic agents acting over real repositories — it can't be specified into existence, it
has to be made **reproducible, observable, and verifiable** during development. Each substrate below
exists because Sculptor depends on something nondeterministic, external, slow, or hard to observe.

#### 10.1 Test doubles & determinism
The single most important piece is **FakeClaude**: a drop-in replacement for the `claude` CLI that
the agent runner launches during tests. Instead of calling a model, it reads the prompt and — when
the prompt carries a `fake_claude:<command>` directive — performs a scripted behavior (emit text,
stream text with delays, write or edit a file, run bash, update a TODO list, ask the user a
question, spawn a subagent, trigger compaction, …) while producing exactly the JSONL stream and
session files the real harness would. This turns the product's most nondeterministic dependency
into a precise instrument: a test can demand a specific sequence of tool calls and assert the UI
that results. A companion primitive, **`FakeClaudePause`**, freezes the fake agent mid-stream and
releases it on command, so transient states (a streaming cursor, a "compacting" indicator, an open
question panel) can be observed deterministically. The same idea recurs for other external
dependencies: CI stubs the real `claude` binary, and **test repo factories** synthesize throwaway
git repositories so tests never depend on a real checkout.

#### 10.2 The end-to-end harness
Frontend integration tests drive the *real* app in a real browser via Playwright, structured as a
**Page Object Model**: a `SculptorInstance` owns the backend process, browser page, and test repo,
and typed page/element objects expose semantic actions ("create a task", "open the diff") instead of
raw selectors. The UI honors a stable **test-id contract** (the `ElementIDs` enum), and integration tests are
tagged with a **`@user_story(...)`** describing the behavior they validate — the thread that links a
test back to a scenario.

#### 10.3 Test taxonomy & fidelity tiers
Tests are stratified by a deliberate determinism-vs-fidelity trade: **unit** tests (colocated,
backend and frontend); **integration** tests (Playwright + FakeClaude, the bulk of user-visible
coverage); **regression** tests (one per fixed bug); and the model-backed **`real_claude`** and
**`real_pi`** tiers that run the same flows against the actual model CLIs to catch protocol drift.
The real-model tiers are slow and cost API usage, so they're excluded from CI and run deliberately.
Further pytest markers segregate tests by **launch mode** — e.g. `electron`, `electron_custom_command`,
and `packaged_electron` (the last combined with `release`) — and by sandbox needs (e.g.
`custom_sculptor_folder`), so a test runs only in the environment it requires.

#### 10.4 Scenarios-as-tests methodology
This spec, the exhaustive **`scenarios.md`** (Given/When/Then behaviors), and
**`scenario_coverage.md`** (which maps each scenario to the integration test covering it) together
form the **English-level acceptance layer**: the spec is the source of truth, the scenarios are
concrete acceptance checks against it, and the coverage report measures how well the product is
actually demonstrated. This methodology is itself testability infrastructure — it is the reason the
scenario corpus exists.

#### 10.5 CI execution substrate
Tests run at scale on **offload**, which fans work out across many parallel sandboxes on Modal
(hundreds for integration, dozens for unit) with a **cached base image** — slow dependency layers are
checkpointed and only a thin source diff is applied per run, keeping feedback fast. A separate
**packaged-test** stage runs the integration suite against the *built* desktop artifact (the
DMG/AppImage), not source, to verify the thing that actually ships — including DMG validation.

#### 10.6 Static quality gates
Beyond tests, a set of gates keeps quality from eroding silently. **Ratchets** are per-rule violation
budgets that can only be reduced, never raised without justification — they let the codebase tighten
over time (e.g. forbidding raw CSS selectors or `time.sleep()` in integration tests, capping
`logger.warning` use). Alongside them: formatting, linting, and type-checking (ruff, eslint,
pyrefly, tsc), a **design-token stylelint plugin** that forbids hardcoded style values, and
file-hygiene and shell checks.

#### 10.7 Cross-surface contract generation
Sculptor has three surfaces over one backend (GUI, CLI, API), kept from drifting by **generation
rather than hand-maintenance**: TypeScript types and the frontend API client are generated from the
FastAPI/OpenAPI schema, the `sculpt` client is generated similarly, and a **frozen model-schema
snapshot** (→ §10.9) detects unintended backend-model changes. A backend-model change that isn't reflected across surfaces shows
up as a regenerated diff or a failing check, not a runtime surprise.

#### 10.8 Build-context data-folder resolution & isolation
Where Sculptor keeps its data is resolved from **build context**, not hardcoded. A single
`get_sculptor_folder()` routine picks `<repo>/.dev_sculptor` when **running from source** (detected by
walking up the tree for a `.git` directory), `~/.dev-sculptor` for a **packaged dev build** (detected
by a `.dev` version suffix), and `~/.sculptor` for a **packaged production build** — where "packaged"
means a PyInstaller bundle (`sys.frozen`), mirrored on the Electron side as `app.isPackaged` so the
shell resolves the same path. Above all of these, a **`SCULPTOR_FOLDER` env override wins outright**,
and that override is the **isolation lever the whole test substrate rests on**: each test — and each
parallel sandbox on offload (§10.5) — runs against a throwaway temp folder (the `custom_sculptor_folder`
marker, §10.3), so suites never touch or race on a developer's real `~/.sculptor` state, and a source
checkout, a dev build, and the shipped app can coexist on one machine without colliding. This
build-context split is exactly what lets the harness run hundreds of backends in parallel against
isolated state.

#### 10.9 Data-durability machinery
User data lives in a local SQLite database, and migrations are first-class: every Alembic migration
ships with a **version test** that exercises the upgrade against representative data, and a frozen
Pydantic-schema snapshot is wired in to guard the versioned JSON fields against unintended change. This is what lets the product evolve its
data model across releases without corrupting users' existing state.

#### 10.10 Diagnosability
Finally, infrastructure for understanding failures that escape the tests: distributed **tracing**,
**Sentry** error reporting, structured logging conventions, in-app **debug / diagnostics** views
(per-agent diagnostics, the chat debug view), the **auto-qa** headless-browser harness for
visual/manual QA, and **Storybook** for inspecting components in isolation.

## 11. Build, Release & Distribution

This section describes how Sculptor is built and how it reaches users.

#### 11.1 Build & packaging

Sculptor ships as a **desktop application** that combines a **React frontend** with a **packaged
backend**, bundled together into an **Electron app** via Electron Forge. The release pipeline builds
for **macOS** (Apple Silicon) and **Linux** (x64, with arm64 as a best-effort, non-blocking target).
The **`sculpt` CLI** is built and
shipped alongside the app (together with a `sculptor_migrate` data-folder migration helper), so the
command-line surface is available wherever Sculptor is installed.

#### 11.2 Release & versioning

Builds flow through three channels. **Dev builds** are cut from `main` (always carrying a `.dev`
version suffix) for everyday testing. From there a release is cut onto a **release branch**, first as
a **release candidate** and then promoted to a **stable release**, with hotfix branches available for
an already-published release. Releases are **tag-driven**: pushing the release tag drives CI to build,
sign, package, and publish the artifacts, and the version is checked against the build context so a
tag build can never publish an inconsistent version.

#### 11.3 Distribution & auto-update

Users download Sculptor as a **signed and notarized macOS `.dmg`** or a **Linux `.AppImage`** (linked
from the README and Imbue's download page). Once installed, the app keeps itself current with **in-app
auto-update**: it detects a newer release on the chosen channel, and a toast offers to **install and
restart** in place — no manual re-download required.

#### 11.4 Help docs

User-facing help lives under **`docs/help/`** — getting started, workspaces, chat, terminal, agents,
changes, pull requests, skills, the command palette, settings, and the experimental container backend.
These docs are **audited and refreshed for each release** so they match the shipped version, including
re-captured screenshots.

## 12. Open Issues

Unresolved questions to settle as the spec matures. Each names a specific place the spec is currently
inconsistent about the §9-product-behavior vs. §10-engineering-substrate line:

- **Do user-facing diagnostics belong in §7 or §10?** The diagnostics a user can actually open — the
  chat **debug view** (and its timestamp toggle), per-agent **diagnostics** from the agent context
  menu, and the **diagnostics** in the version popover — are currently filed under §10.10
  (Diagnosability) as engineering substrate, yet they're user-visible features that would otherwise
  belong in §7. They're documented in neither place right now. Decide the rule (user-openable ⇒ §7?)
  and apply it.
- **Auto-update is split across three sections** with no single home: the version popover and update
  toasts (§7.9), the guarantee that updating preserves your work (§9.5), and the update mechanism
  (§11.3). Confirm this is intentional faceting rather than something to consolidate.
- **The cross-surface consistency guarantee** — that a workspace or agent created via `sculpt`
  appears in the GUI and vice versa — is asserted in §5 and §8 but has no entry among the §9
  guarantees, where a user-facing cross-cutting promise would normally live. Decide whether to add
  one.

## Appendix A — Glossary

The core nouns are defined in §6 (Core Domain Model). This is a quick reference for secondary terms
used throughout:

- **Target branch** — the branch a workspace's changes and pull request are measured against.
- **Plan mode** — an agent investigates and proposes a plan for your approval before changing files.
- **Fast mode** — trades some response depth for quicker output.
- **Effort** — how much thinking an agent spends per step (Low … Max).
- **Peek** — the hover popover previewing another workspace's agents, branch, and status.
- **CI babysitter** — an opt-in helper that watches a pull request's CI and asks an agent to fix
  failures.
- **Slug** — the short feature identifier the workflow skills (spec → … → review) use to find each
  other's artifacts.
- **Skill** — a reusable, slash-invoked workflow that runs as its own agent.
- **Zen / Focus mode** — view modes that hide panels (and, for zen, the top bar) to maximize the chat.
