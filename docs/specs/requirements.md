# Sculptor — Requirements

This document specifies the product's measurable targets, limits, compatibility bars, data and
integration contracts, and cross-cutting guarantees as they exist today.

## How to read this document

This is the requirements leg of the specification set. `SPEC.md` describes *what the product is and
how each feature behaves*; this document pins the **measurable and contractual** facts that prose
deliberately leaves out — numeric targets, version/platform bars, persistence and migration
guarantees, integration contracts, and where the product is intentionally configurable or currently
unspecified.

| Document | Answers | Layer |
|---|---|---|
| `SPEC.md` | *What is the product, and how does each feature behave?* | Functional behavior, in prose |
| `scenarios.md` | *What exactly happens on screen, action by action?* (Given/When/Then) | UI-level acceptance |
| `scenario_coverage.md` | *Which test demonstrates each scenario?* | Coverage / traceability to tests |
| **`requirements.md`** (this doc) | *What measurable targets, limits, and contracts does the product meet?* | Requirements |

**This document does not restate functional behavior.** Where a requirement is "behave as described,"
it points at the spec section and scenario area rather than re-deriving the behavior (which would
duplicate and drift). What it adds is everything the descriptive spec intentionally omits.

### Conventions

- **Requirement IDs** are stable (`REQ-<AREA>-NNN`) so tests, tickets, and reviews can cite them.
  Areas: `FUNC` (functional), `NFR` (non-functional, measurable), `COMPAT` (platform/deps),
  `DATA` (persistence/migration), `INT` (external integrations), `SEC` (security/privacy/telemetry).
- **RFC 2119 keywords**, scoped to the product: **MUST** = a guarantee the product always upholds;
  **SHOULD** = the product's default/expected behavior, with deliberate or configurable exceptions;
  **MAY** = optional or user-configurable.
- **Criticality** — how central a capability is to the product: **Core**, **Standard**, **Optional**,
  **Experimental**. (Experimental capabilities are opt-in; see `SPEC.md` §7.12.)
- **Source values** are quoted from the current implementation with repo-relative `path:line`
  citations, so each number in this doc is verifiable. A requirement tagged **[Unspecified]** is one
  the product does **not** currently pin down — these are real gaps in the specification, collected in
  §7 (Open questions).
- Citations use repo-relative paths; line numbers are as of this writing and may drift — treat the
  symbol/constant name as the durable reference.

---

## 1. Functional requirements

The functional behavior lives in `SPEC.md` §7–§8 and is verified, action-by-action, by `scenarios.md`.
Rather than copy it, this section indexes the product's capabilities with a criticality rating and
pointers to their spec/scenario home.

| ID | Capability | Spec | Scenarios | Criticality |
|---|---|---|---|---|
| REQ-FUNC-001 | Onboarding & connecting a repo (wizard, dependency checks, repo add/init) | §7.1 | `ONB`, `ADDREPO` | Core |
| REQ-FUNC-002 | Workspaces: create (worktree default), banner, setup command, lifecycle, delete | §7.2 | `ADDWS`, `WS` | Core |
| REQ-FUNC-003 | Rich chat agent loop: compose/send, streaming, tools, status, steer (stop/queue/interrupt), questions, footer, errors | §7.3.1 | `CHAT`, `MSG` | Core |
| REQ-FUNC-004 | `/btw` read-only side question | §7.3.1 | `CHAT` | Optional |
| REQ-FUNC-005 | Terminal agents (plain Terminal + registered, e.g. "Claude CLI") | §7.3.2 | `WS`, `CHAT` | Standard |
| REQ-FUNC-006 | Multiple agents per workspace: tabs, status dots, create/rename/reorder/delete, peek, subagents, background tasks | §7.4 | `WS`, `CHAT` | Core |
| REQ-FUNC-007 | Changes: Browse/Changes/Commits, diff view, scope picker, discard, commit | §7.5 | `PANEL` | Core |
| REQ-FUNC-008 | Pull/Merge requests: create, status dots, detail dropdown, retarget, CI babysitter toggle | §7.6 | `WS` | Core |
| REQ-FUNC-009 | Built-in workspace terminal(s) | §7.7 | `PANEL` | Standard |
| REQ-FUNC-010 | Skills & workflows: picker, library panel, `sculptor-workflow` pipeline, `fix-bug`, `setup-repo` | §7.8 | `SKILL`, `CMDP` | Standard |
| REQ-FUNC-011 | Command palette & navigation: tabs, Cmd+K / Cmd+P, bottom bar, focus/zen mode, version popover | §7.9 | `SHELL`, `CMDP`, `HELP` | Core |
| REQ-FUNC-012 | Settings (all sections) | §7.10 | `SET` | Core |
| REQ-FUNC-013 | Actions & notes; mentions & path autocomplete | §7.11 | `ACT`, `MENT` | Optional |
| REQ-FUNC-014 | Experimental surface (toggles, experimental skills/panels, frontend plugin system, container backend) | §7.12 | `SET`, `PANEL` | Experimental |
| REQ-FUNC-015 | `sculpt` CLI: full command surface, `--json`, env-var defaults, cross-surface visibility | §8 | (CLI-level, see §5.4) | Standard |

- **REQ-FUNC-100 (MUST).** Every behavior enumerated in `scenarios.md` is a product requirement; that
  corpus — not the table above — is the exhaustive functional contract, and `scenario_coverage.md`
  measures how well each behavior is demonstrated by an automated test. The table only rates
  criticality.
- **REQ-FUNC-101 (MUST).** **Cross-surface consistency.** A Workspace or Agent created via `sculpt`
  MUST appear in the GUI, and vice versa, because both surfaces are clients of one local backend over
  one persisted store (`SPEC.md` §5, §8). _This is `SPEC.md` Open Issue #3 — it has no §9 guarantee
  there today; this requirement is its home._
- **REQ-FUNC-102 (SHOULD).** Feature gating: every capability marked experimental in `SPEC.md` §7.12
  is opt-in and off by default, **except** Smooth streaming, which is on by default (`SPEC.md` §7.12).

---

## 2. Non-functional requirements (measurable)

`SPEC.md` §9 states the cross-cutting guarantees qualitatively ("the UI stays live," "durable,"
"make progress in parallel"). This section attaches the **measurable bars** the product holds to,
and flags the targets it does not currently define.

### 2.1 Responsiveness & live updates (→ SPEC §9.4)

- **REQ-NFR-001 (MUST).** Agent output, status changes, and file-change indicators appear in the UI
  without manual refresh, driven by the live update stream (full snapshot on connect, then deltas).
- **REQ-NFR-002 (SHOULD).** Default in-flight request timeout is **10 s**
  (`sculptor/frontend/src/common/state/requestTracking.ts`); a request exceeding it surfaces an error
  rather than hanging.
- **REQ-NFR-003 (SHOULD).** UI debounce/throttle budgets that shape perceived responsiveness:
  - agent status: **500 ms** (`.../chat-alpha/useAgentStatus.ts`)
  - auto-scroll / jump-to-bottom / in-file search: **150 ms** (`.../chat-alpha/hooks/`, `diffPanel/useInFileSearch.ts`)
  - active-prompt scroll throttle: **100 ms**; mark-read: **1000 ms**; panel-layout sync: **2000 ms**
  - branch-name preview: **250 ms**; branch-name collision check: **300 ms** (`add-workspace/hooks/useBranchNamePreview.ts`)
- **REQ-NFR-004 [Unspecified].** The product defines no explicit end-to-end **streaming latency**
  budget (model token emitted → rendered) or **interaction latency** (click → visible response) target.
  → OPEN-1 (§7).

### 2.2 Concurrency & scale (→ SPEC §9.2)

- **REQ-NFR-010 (MUST).** Many agents across many workspaces run concurrently and make independent
  progress. Agents in the **same** workspace share files with **no locking** — this is documented,
  accepted behavior, not a defect (`SPEC.md` §9.2, §7.4).
- **REQ-NFR-011 (SHOULD).** PR/CI status polling runs a bounded worker pool of **4** with a global
  minimum spacing of **1.5 s** between provider API calls across workers, so polling cannot stampede a
  provider (`sculptor/sculptor/web/pr_polling_service.py`).
- **REQ-NFR-012 [Unspecified].** The product enforces **no cap** on max concurrent agents, max
  workspaces, or subagent fan-out (searched; none found). Whether these should be bounded — and the
  resource model that makes "uncapped" safe — is undefined. → OPEN-2 (§7).

### 2.3 Crash recovery & resumption (→ SPEC §9.3)

- **REQ-NFR-020 (MUST).** Quit/crash + reopen restores all workspaces, agents, and full conversation
  history. A running agent is reattached/resumed where possible; an unanswered question asked before
  the interruption remains answerable after reopen.
- **REQ-NFR-021 (MUST).** Failures surface visibly (never silent); an errored agent SHOULD offer a
  restore/continue path unless its workspace was deleted.
- **REQ-NFR-022 (SHOULD).** Resumption uses the agent CLI's own session continuation (Claude
  `--resume <session_id>`; Pi `--session-dir`+`--session-id`) and tolerates a **corrupt session tail**
  by resuming from the valid prefix
  (`sculptor/sculptor/agents/default/claude_code_sdk/process_manager_utils.py`). See REQ-INT-021.

### 2.4 Persistence & durability (→ SPEC §9.5)

- **REQ-NFR-030 (MUST).** Workspaces, agents, full conversation history, and settings persist locally
  and survive both restart and in-place upgrade to a newer app version. (Detailed data requirements:
  §4.)
- **REQ-NFR-031 (SHOULD).** The local DB runs in **WAL** journal mode with a **15 s** busy timeout to
  tolerate concurrent access (`sculptor/sculptor/database/core.py`).

### 2.5 Custom/remote backend timing (→ SPEC §7.12, §9.1)

- **REQ-NFR-040 (SHOULD).** Backend-readiness timeout (app waits for the launcher's printed URL):
  **20 s** production, **10 s** dev, **60 s** testing (`sculptor/frontend/src/electron/main.ts`). The
  app auto-restarts a crashed custom backend with backoff.
- **REQ-NFR-041 [Unspecified].** The custom-backend restart **backoff schedule** (base, factor, cap,
  max attempts) is delegated to the retry library and not pinned in product config. → OPEN-3 (§7).

### 2.6 Diff & input limits

- **REQ-NFR-050 (SHOULD).** A diff over **500 lines** is gated behind "Show full diff"
  (`.../diffPanel/LargeDiffGate.tsx`). Binary files and renames/deletes show an explanatory banner
  instead of a diff (`SPEC.md` §7.5).
- **REQ-NFR-051 (SHOULD).** Max single file/image upload is **20 MB**
  (`sculptor/frontend/src/components/FileUploadUtils.ts`).
- **REQ-NFR-052 [Unspecified].** Max **attachment count** per message is not enforced. → OPEN-4 (§7).
- **REQ-NFR-053 (MAY).** Default file-browser split ratio is **50/50**; split-vs-unified, wrapping,
  and tab-close behavior are user-configurable (`sculptor/sculptor/config/user_config.py`; `SPEC.md` §7.10).

### 2.7 Polling & freshness defaults

- **REQ-NFR-060 (SHOULD).** PR/CI status polling defaults: interval **30 s**, floor **10 s**;
  closed-workspace multiplier **6×**; merged/closed (terminal) multiplier **10×**; not-ready retry
  **30 s**; provider rate-limit cooldown **60 s** (`sculptor/sculptor/config/user_config.py`,
  `sculptor/sculptor/web/pr_polling_service.py`). Interval and multiplier are user-configurable (`SPEC.md` §7.10).
- **REQ-NFR-061 (SHOULD).** Local workspace/remote-branch polling interval is **3 s**
  (`sculptor/sculptor/web/repo_polling_manager.py`); git-info lookups time out at **10 s**, branch-name preview
  git calls at **5 s**.
- **REQ-NFR-062 (SHOULD).** CI babysitter defaults: **off**, retry cap **3**
  (`sculptor/sculptor/config/user_config.py`).

### 2.8 Agent defaults

- **REQ-NFR-070 (MUST).** New-agent defaults: model = the user's **configured Settings default** if
  set, else the **most-recently-used** model (recorded whenever the user switches model in chat;
  `lastUsedModelAtom`, `sculptor/frontend/src/common/state/atoms/userConfig.ts`), else a hardcoded
  fallback of **`CLAUDE_4_OPUS` ("Opus (1M)")**, the 1M-context Opus variant (Fable, though listed in
  the switcher, is disabled and so is never the fallback). Effort = **Extra High (`xhigh`)**, fast mode
  = **off** (`sculptor/sculptor/config/user_config.py`, `sculptor/sculptor/web/derived.py`). All three
  are user-overridable in Settings → Agent (`SPEC.md` §7.10). **Fast mode** is offered only on models
  that support it — the Opus 4.x family, including Opus 4.8 (both the 1M and 200K variants) — and is
  disabled for Sonnet/Haiku/Fable (`sculptor/frontend/src/common/modelCapabilities.ts`).

---

## 3. Platform & dependency compatibility (→ SPEC §11)

`SPEC.md` §11 names the OS targets; this section pins the versions the product builds, runs, and
depends on.

### 3.1 Build & runtime platforms

- **REQ-COMPAT-001 (MUST).** Sculptor ships a **macOS (Apple Silicon / arm64)** build. macOS x64 is
  **not** a target (CI builds arm64 only; the managed Claude binary has no darwin-x64) —
  `.github/workflows/build-desktop.yml`, `sculptor/sculptor/services/managed_tools.py`.
- **REQ-COMPAT-002 (SHOULD).** Sculptor ships a **Linux x64** build; **Linux arm64** is best-effort /
  non-blocking (`.github/workflows/build-desktop.yml`; `SPEC.md` §11.1).
- **REQ-COMPAT-003 [Unspecified].** The supported **minimum macOS version** is not stated as a
  product requirement (CI builds/tests on macOS 14 Sonoma; Electron 42's own floor is macOS 12), and
  the **minimum Linux glibc** is likewise unpinned. → OPEN-5 (§7).

### 3.2 Toolchain / framework baselines

The product is built against the following baselines (informational; relevant to anyone building or
packaging Sculptor):

| Component | Pinned value | Source |
|---|---|---|
| REQ-COMPAT-010 Python | **>=3.14, <3.15** (pinned 3.14) | `pyproject.toml`, `.python-version` |
| REQ-COMPAT-011 Node.js | **24.17.0** | `sculptor/frontend/.nvmrc` |
| REQ-COMPAT-012 Electron | **42.4.1** (Forge **7.11.2**) | `sculptor/frontend/package.json` |
| REQ-COMPAT-013 uv (Python pkg mgr) | **>=0.11.22** | `pyproject.toml` |
| REQ-COMPAT-014 TypeScript / React / Jotai / Radix Themes / Vite | **6.0 / 19.2 / 2.20 / 3.3 / 6.4** | `sculptor/frontend/package.json` |

### 3.3 Required external binaries

- **REQ-COMPAT-020 (MUST).** **Claude CLI** is required. Compatibility window: **recommended 2.1.195,
  minimum 2.1.195, maximum 2.99.99, blocked 2.1.101**; supported platforms **darwin-arm64** and
  **linux-x64** (`sculptor/sculptor/services/managed_tools.py`). Sculptor can install/manage it and can use a
  user-supplied binary (`SPEC.md` §7.1, §7.10).
- **REQ-COMPAT-021 [Unspecified].** **Git** is required and is **runtime-detected with no
  minimum-version check** (searched; none found). The minimum supported git version is undefined
  (worktree support is the relevant capability). → OPEN-6 (§7).
- **REQ-COMPAT-022 (SHOULD).** The **Pi** harness (experimental agent) pins **0.78.0**; platforms
  darwin-arm64, darwin-x64, linux-x64, with per-platform sha256 checksums
  (`sculptor/sculptor/services/managed_tools.py`). A version mismatch fails clearly (REQ-INT-022).
- **REQ-COMPAT-023 (MUST, conditional).** The PR/MR surface requires the matching provider CLI —
  **`gh`** (GitHub) or **`glab`** (GitLab) — present and authenticated; absence/non-auth degrades to a
  documented error state, never a crash (§5.1, `SPEC.md` §7.6).

---

## 4. Data persistence, durability & migration (→ SPEC §9.5, §10.8)

`SPEC.md` quarantines SQLite/Alembic as implementation. They are first-class here because the product
makes durability and upgrade-survival guarantees (§9.5) that rest directly on this layer.

### 4.1 On-disk layout & store

- **REQ-DATA-001 (MUST).** User data lives in a single **Sculptor folder**: `~/.sculptor` (stable),
  `~/.dev-sculptor` (dev builds), or `<repo>/.dev_sculptor` (running from source), overridable via the
  `SCULPTOR_FOLDER` env var; the workspaces path is separately overridable via
  `SCULPTOR_WORKSPACES_FOLDER` (`sculptor/sculptor/utils/build.py`).
- **REQ-DATA-002 (MUST).** Within it: `internal/database.db` (SQLite), `internal/config.toml`
  (settings), `internal/logs/`, `internal/uploads/`, `internal/artifacts/`, `workspaces/`, and a
  top-level `.format_version` marker (`sculptor/sculptor/utils/build.py`, `sculptor/sculptor/utils/migration.py`).
- **REQ-DATA-003 (MUST).** The store keeps an **append-only immutable snapshot table per entity plus a
  materialized `<entity>_latest` view maintained by DB triggers**; the immutable log is the source of
  truth (`sculptor/sculptor/database/core.py`, `automanaged.py`). The externally-observable guarantee is that
  full history is retained and current state is cheap to read.
- **REQ-DATA-004 (MUST).** Persisted entities: **UserSettings, Project, Workspace, Task,
  SavedAgentMessage, Notification** (`sculptor/sculptor/database/models.py`). _("Task" is the vestigial internal
  primitive backing an Agent — see `SPEC.md` §6; it is a storage concern, not a product concept.)_

### 4.2 Durability & upgrade survival

- **REQ-DATA-010 (MUST).** Settings, the database (projects/workspaces/agent history/messages),
  workspace directories, logs, and uploads survive an in-place app upgrade (covered by
  `test_migration.py`; `SPEC.md` §9.5).
- **REQ-DATA-011 (MUST).** Alembic migrations run automatically at startup, upgrading the DB to head;
  a detected **downgrade** (DB newer than app) fails with a clear, actionable error rather than
  corrupting data (`sculptor/sculptor/database/core.py`). Migrations are **forward-only** in practice
  (downgrade stubs are mostly no-ops).
- **REQ-DATA-012 (MUST).** Every Alembic migration ships a **companion version test** under
  `sculptor/sculptor/database/alembic/version_tests/` (seed → migrate → verify), enforced by
  `test_every_migration_has_a_test_fixture()` (`sculptor/sculptor/database/README.md`) — the process guarantee
  that lets the schema evolve safely.
- **REQ-DATA-013 (MUST).** Versioned JSON columns (e.g. `Task.task_inputs`, `SavedAgentMessage.message`,
  which store unions of agent-message/input variants) are guarded by a **frozen Pydantic-schema
  snapshot** (`alembic/frozen_pydantic_schemas.json`); a model change that isn't reflected fails a test
  until a migration is authored or the change is confirmed back-compatible (`alembic/json_migrations.py`).

### 4.3 Backward compatibility & folder migration

- **REQ-DATA-020 [Unspecified].** The product does not state a **back-compat horizon** — how far back
  older data folders / DB versions are guaranteed readable. → OPEN-7 (§7).
- **REQ-DATA-021 (SHOULD).** A **data-folder migration helper** (`sculptor_migrate`, i.e.
  `scripts/migrate_sculptor_folder.py`) relocates/restructures the folder (legacy `~/.sculptor_data`
  → `~/.sculptor`): it is **idempotent** and **resumable** (renames to `.migrating`), backs up the DB
  via SQLite native backup, rewrites embedded workspace paths (`workspace.environment_id` / `_latest`),
  migrates Claude session folders to match new workspace paths, and writes `.format_version`.
- **REQ-DATA-022 (SHOULD).** Startup tolerates an old/unversioned folder by bootstrapping the
  structure and writing `.format_version` (`sculptor/sculptor/utils/migration.py`); config loading tolerates
  legacy fields via model validators (e.g. old `claude_binary_mode` folding, invalid `custom_actions`
  silently dropped) rather than crashing (`sculptor/sculptor/config/user_config.py`).

---

## 5. External integration contracts (→ SPEC §5, §6, §7.6, §8)

Each external boundary is a contract the product upholds, **including its failure modes** — the spec
describes the happy path and the error *surfaces*; this section pins the contract and the degradation
rules behind them.

### 5.1 Git host providers

- **REQ-INT-001 (MUST).** The provider is detected from the `origin` remote hostname (parsing SSH and
  HTTP(S) forms): hostname containing **"github"** → GitHub via **`gh`**; containing **"gitlab"** →
  GitLab via **`glab`**. Any other host has **no** PR/MR surface (`SPEC.md` §7.6;
  `sculptor/sculptor/web/pr_polling_service.py`). The **target-branch** selector is *not* gated on the
  provider, however — it is host-independent and available on every repo, including repos with no
  remote (which offer the repo's local branches as targets); only opening a PR/MR requires a detected
  provider (`SPEC.md` §7.2 / §7.5; `sculptor/sculptor/web/repo_polling_manager.py` target-branch
  fallback).
- **REQ-INT-002 (MUST).** Operations performed via the provider CLI: **list** requests for a branch,
  **view** a request's status-check/pipeline rollup, **reviews/approvals**, and **unresolved
  comments/discussions**; **push** the branch and **open** a request; poll status thereafter. (GitHub:
  `gh pr list/view`; GitLab: `glab mr list/view` + `glab api …/approvals` and `…/discussions`.)
- **REQ-INT-003 (MUST).** The failure taxonomy is classified and surfaced distinctly (not collapsed
  into "error"): **cli_missing**, **not_authenticated**, **rate_limited** (→ 60 s host cooldown),
  **network_error** (permanent) vs **transient** (retried once)
  (`sculptor/sculptor/web/cli_status_utils.py`, `pr_polling_service.py`). Each maps to the actionable
  warning/info button states in `SPEC.md` §7.6.

### 5.2 Agent model CLIs

- **REQ-INT-021 (MUST).** **Claude** is launched as a long-lived process speaking **stream-json over
  JSONL** on stdin/stdout (with `--verbose`, hook events, MCP config, and `AskUserQuestion`/`ExitPlanMode`
  disallowed so Sculptor renders those itself); resumed with `--resume <session_id>`. Session files at
  `~/.claude/projects/-code/<session_id>.jsonl` are validated (≥1 user/assistant message with matching
  `sessionId`) and **a corrupt tail is tolerated** by reading the valid prefix
  (`sculptor/sculptor/agents/default/claude_code_sdk/process_manager_utils.py`). The contract — not the exact
  flags — is the requirement; flags track the upstream CLI (REQ-COMPAT-020).
- **REQ-INT-022 (SHOULD).** **Pi** is launched in **`--mode rpc`** with `--session-dir`/`--session-id`
  (same dir+id resumes); multiplexed JSONL channels (`response`, `extension_ui_request`,
  `AgentSessionEvent`); API keys injected from named env vars at startup and **never persisted**; a
  version mismatch raises a clear error (`sculptor/sculptor/agents/pi_agent/agent_wrapper.py`). Pi
  reports a live model catalog and supports **in-session model switching** via a `set_model` RPC
  between turns (a rejected switch raises `PiSetModelError` → HTTP 400, surfaced as a toast); a turn
  that ends in a **known-transient provider error** (overload, 429, 5xx/529, timeout) is retried
  automatically with exponential backoff (up to 4 attempts, honoring a user interrupt during backoff)
  rather than crashing the agent, exhausting to a re-runnable error message (`output_processor.py`).
- **REQ-INT-023 (MUST).** A missing binary for either CLI raises a specific, surfaced error
  (`ClaudeBinaryNotFoundError` / `PiBinaryNotFoundError`), not a generic failure.

### 5.3 Terminal-agent registration

- **REQ-INT-030 (SHOULD).** Registered terminal agents are TOML files under
  `<sculptor_folder>/terminal_agents/`, one per agent, keyed by **`registration_id` = filename stem**
  (must match `[a-z0-9][a-z0-9_-]*`), declaring **`display_name`** (required), **`launch_command`**
  (required), **`resume_command_template`** (optional), **`accepts_automated_prompts`** (optional,
  default false) (`sculptor/sculptor/services/terminal_agent_registry/registry.py`).
- **REQ-INT-031 (SHOULD).** Placeholders are substituted by literal replacement (not `.format()`):
  `{sculptor_directory}` and `{terminal_agents_directory}` in `launch_command`; those plus **at most
  one** `{session_id}` in `resume_command_template`; unknown placeholders are rejected. The directory
  is **re-read on demand** (no restart needed to add an agent), and launch params are **stamped onto the
  agent at creation** so it survives later edits/deletion of the file (`SPEC.md` §7.3.2; `registry.py`).

### 5.4 `sculpt` CLI ↔ backend

- **REQ-INT-040 (SHOULD).** `sculpt` reaches the local backend at `http://localhost:<port>` where port
  = **`SCULPT_API_PORT`** (default **5050**), or an explicit `--base-url`; it fetches a session token
  and sends it as the `x-session-token` header. A connection failure exits with a clear "could not
  connect to Sculptor server" message (`tools/sculpt/sculpt/auth.py`).
- **REQ-INT-041 (SHOULD).** The CLI client is **generated** from the backend OpenAPI schema (same
  contract as the GUI client) — see `SPEC.md` §10.7 and the Appendix. Env-var defaults
  (`SCULPT_WORKSPACE_ID`, `SCULPT_AGENT_ID`, `SCULPT_PROJECT_ID`) and short-prefix IDs work as in
  `SPEC.md` §8.

### 5.5 Environment-variable injection

- **REQ-INT-050 (SHOULD).** Sculptor loads a **global `~/.sculptor/.env`** and a **per-repo
  `.sculptor/.env`**, with **project values overriding global**, injecting them into agent/terminal
  environments; the format supports `KEY=value`, `export KEY=value`, quotes, and `#` comments
  (`sculptor/sculptor/services/workspace_service/environment_manager/env_file_parser.py`; `SPEC.md` §7.10). An
  override toggle governs whether these replace pre-existing variables.

---

## 6. Security, privacy & telemetry (→ SPEC §9.1, §9.6, §9.7)

- **REQ-SEC-001 (MUST).** **Trust boundary.** By default an agent works only inside its isolated
  workspace copy and MAY run real shell commands there; **nothing is pushed to a remote and no PR/MR is
  opened without an explicit user action**. In-place mode (editing the real checkout) and the
  container/remote backend are the deliberate, opt-in exceptions (`SPEC.md` §9.1). This boundary holds
  for both the GUI and `sculpt`.
- **REQ-SEC-002 (MUST).** **Local-first, single-user.** Code and secrets stay on the user's machine;
  Imbue does not store repositories or train on user code (`SPEC.md` §9.6). Pi API keys and similar
  secrets are read from the environment and **never persisted to config** (REQ-INT-022).
- **REQ-SEC-003 (MUST).** Build & distribution security: the macOS artifact is **signed and notarized**
  (`.dmg`); releases are **tag-driven** with the version checked against build context so a tag build
  cannot publish an inconsistent version (`SPEC.md` §11.2–§11.3).
- **REQ-SEC-004 (Experimental).** **Frontend-plugin trust model.** The experimental frontend plugin
  system (off by default, gated on the `enableFrontendPlugins` flag — atom
  `isFrontendPluginsEnabledAtom`, default `false`) runs plugin code **in the renderer with the same
  privileges as Sculptor's own UI**; a URL plugin source is re-fetched on every load, so the user
  trusts whatever it serves at load time. Adding a plugin source is therefore equivalent to running
  that code, documented in `SECURITY.md`. The SDK's `openExternal` is restricted to **`http(s)`**
  URLs (`sculptor/frontend/src/plugins/sdk/actions.ts`). In the packaged app the renderer and its
  plugins are served from a single secure custom origin (`sculptor://app`) rather than `file://`
  (`sculptor/frontend/src/electron/appProtocol.ts`). Plugins load from the Sculptor folder's
  `plugins/` directory or user-added URL sources; precedence is local-disk > URL > bundled for the
  same plugin id (`SPEC.md` §7.12).
- **REQ-SEC-010 (MUST).** **Telemetry is consent-gated.** Error reporting (Sentry, frontend-only) and
  product analytics (PostHog) are each gated on explicit consent flags
  (`is_error_reporting_enabled`, `is_product_analytics_enabled`, `is_session_recording_enabled`,
  `is_telemetry_level_set`, `is_privacy_policy_consented`) and the choice persists across restarts
  (`sculptor/sculptor/config/user_config.py`; `SPEC.md` §9.7). Product telemetry masks private content
  (file/branch names, prompts).
- **REQ-SEC-011 [Unspecified].** **Default-state discrepancy.** `SPEC.md` §7.1/§9.7 describe telemetry
  as *opt-out / on by default*, but the stored consent flags **default to `false`** until the user
  makes a choice. Which is authoritative (the onboarding default vs. the persisted default) is
  unresolved, and spec and code should be reconciled. → OPEN-8 (§7).

---

## 7. Open questions & unspecified behaviors

Consolidated from the **[Unspecified]** tags above — points where the product currently pins **no**
value, so this specification is genuinely incomplete until each is decided and the relevant requirement
updated.

| ID | Open question | Requirement |
|---|---|---|
| OPEN-1 | Streaming & interaction **latency budgets** + how they're measured | REQ-NFR-004 |
| OPEN-2 | **Concurrency caps** (max agents / workspaces / subagent fan-out), or a documented "safe uncapped" resource model | REQ-NFR-012 |
| OPEN-3 | Custom-backend **restart backoff schedule** | REQ-NFR-041 |
| OPEN-4 | Max **attachment count** per message | REQ-NFR-052 |
| OPEN-5 | Supported **minimum macOS version** and **Linux glibc** floor | REQ-COMPAT-003 |
| OPEN-6 | **Minimum git version** | REQ-COMPAT-021 |
| OPEN-7 | **Data back-compat horizon** — which prior `~/.sculptor` DB/folder versions are guaranteed readable | REQ-DATA-020 |
| OPEN-8 | Telemetry **default state** — reconcile spec's opt-out/on-by-default with the code's default-false consent flags | REQ-SEC-011 |

These complement, and do not duplicate, `SPEC.md` §12 (which tracks the §9-product-vs-§10-substrate
line); resolving §12 may add or retire requirements here.

---

## Appendix — relationship to the test & quality substrate

The verification machinery the product depends on (FakeClaude determinism, the Playwright POM +
`ElementIDs` test-id contract, the fidelity tiers, ratchets, contract generation, migration version
tests, diagnosability) is documented in `SPEC.md` §10 and is **not** re-specified here — but note that
several requirements above are only *checkable* because that substrate exists: REQ-FUNC-100 (scenarios
as acceptance), REQ-DATA-012/013 (migration + frozen-schema tests), REQ-INT-041 / REQ-COMPAT-014
(generated cross-surface clients). Treat `SPEC.md` §10 as the binding companion to this document.
