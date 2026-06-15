# Backend review — flagged issues triage

The backend-review batch run (`agent_docs/backend-review/_prompt.md`, applied to
every non-test Python file) fixed issues by default and **flagged** only those
that genuinely need a human decision. This file collects all flagged items with
their disposition.

**Status:** all Tier 1 and Tier 2 flags (#1–#8) have been resolved. Tier 3 and
Tier 5 remain outstanding (deferred / backlog); Tier 4 is intentional no-action.

- **22 flags across 19 files** at triage time. Severity: 4 MEDIUM, 18 LOW. (No
  HIGH/CRITICAL — the 3 HIGH findings in the run were all fixed in the per-file
  changes.)
- The per-file `agent_docs/backend-review/<path>.md` reports the run produced are
  **no longer kept** — this directory retains only this file and `_prompt.md`.
  Line numbers below are from those original reports and may be stale.
- "Bucket" refers to the prompt's five FLAG-only buckets: #1 ambiguous intent,
  #2 true external contract, #3 needs test changes, #4 architectural/out-of-scope,
  #5 non-obvious security.
- Behavioral fixes (#1) were extracted to the **backend-review bug-fix branch**
  (`saeed/fix/backend-review-bugs`); dead-code removals (#2, #3) and the Tier 2
  refactors (#4–#8) live on the **cleanup branch** stacked on top of it.

---

## Tier 1 — Real bugs / behavioral gaps (highest value)

### 1. `_is_stopping` is never assigned — stop-suppression silently dead  ✅ RESOLVED
- **File:** `sculptor/sculptor/agents/default/agent_wrapper.py`
- **Issue:** `_is_stopping: bool` was declared and read in the clean-exit branch
  of `_handle_user_message` (`if not self._is_stopping:`), but **never written**
  anywhere, so the guard was always true and a `RequestSuccessAgentMessage` was
  emitted on a clean turn exit even when the turn was being stopped.
- **Bucket:** #1 (ambiguous intent).
- **Resolution:** Set `self._is_stopping = True` in the stop handler (covers the
  default agent — claude_code_sdk + pi_agent — and hello_agent's overridden
  handler) so the guard fires; added regression tests for both. On the bug-fix
  branch, commit *"Fix stopped turns emitting a spurious RequestSuccessAgentMessage"*.

### 2. Unreachable `except ProcessError` in startup cleanup  ✅ RESOLVED
- **File:** `sculptor/sculptor/services/workspace_service/environment_manager/default_implementation.py`
- **Issue:** `cleanup_stale_environments` wrapped a DB transaction, `Path.iterdir()`,
  and `shutil.rmtree(...)` in `except ProcessError`, but none spawn a subprocess,
  so the handler was unreachable.
- **Bucket:** #1 (ambiguous intent).
- **Resolution:** Removed the dead handler (born dead — the refactor that created
  this function dropped the subprocess predecessor but copied the handler onto a
  pure DB+filesystem body); de-indented the body and dropped the now-unused
  imports. Commit *"Remove dead error handler, dead CLI flag, and orphan scripts"*.

### 3. Dead `--dist-dir` CLI flag on 5 release commands  ✅ RESOLVED
- **File:** `sculptor/builder/cli.py` — `cut_release`, `fixup_release`,
  `hotfix_release`, `promote_release`, `publish_build_artifacts`
- **Issue:** Each declared `dist_dir: Path = typer.Option("../dist", ...)` that
  was never read — accepted on the CLI but did nothing.
- **Bucket:** #2 (public CLI flag / external contract).
- **Resolution:** Removed the option from all five commands (the release pipeline
  was migrated to `builder/artifacts.py` and the flag had been an inert no-op).
  The unrelated local `dist_dir` in the build command is untouched. Commit
  *"Remove dead error handler, dead CLI flag, and orphan scripts"*.

---

## Tier 2 — Worthwhile refactors, cross-layer  ✅ ALL RESOLVED

### 4. `get_all_workspaces` returned `list[dict[str, Any]]`  ✅ RESOLVED
- **Files:** `sculptor/sculptor/services/data_model_service/data_types.py`,
  `.../sql_implementation.py`, consumer in `web/app.py`
- **Issue:** Fixed-key denormalized rows returned as ad-hoc dicts; style guide
  requires Pydantic models for static-key structured data.
- **Bucket:** #4 (architectural — crosses data-service → web layer).
- **Resolution:** Added `WorkspaceListingRow` (`FrozenModel`) in the data-model
  layer; the web consumer maps it via attribute access. Commit *"Return a typed
  model from get_all_workspaces"*. Note: the model omits the `harness` field —
  `Workspace.harness` was removed upstream on `main`, so it is no longer part of
  the listing.

### 5. `get_commit_history` returned ad-hoc dicts  ✅ RESOLVED
- **Files:** `sculptor/sculptor/services/workspace_service/api.py`,
  `.../default_implementation.py`
- **Issue:** Commit metadata returned as `list[dict]`/`dict[str, dict]` with
  fixed keys.
- **Bucket:** #4.
- **Resolution:** Added `CommitRecord` / `CommitFileChange` (`FrozenModel`) in the
  workspace_service api layer; the impl builds them and the web layer maps them.
  Commit *"Return typed commit records from get_commit_history"*.

### 6. Interface contractually raised builtin `FileNotFoundError`  ✅ RESOLVED
- **File:** `sculptor/sculptor/services/git_repo_service/`
- **Issue:** The git-repo read interface documented raising `FileNotFoundError`;
  the style guide bans raising handleable builtins.
- **Bucket:** #2 (cross-service contract).
- **Resolution:** Added `GitRepoNotFoundError(GitRepoError)`; raised it from the
  repo-missing sites, updated the docstring contract and every catcher
  (`repo_polling_manager` plus three `web/app.py` handlers the original flag had
  missed). Commit *"Replace builtin exception + NamedTuple with domain types"*.

### 7. `SkillSourceDirectory` was a `NamedTuple`  ✅ RESOLVED
- **File:** `sculptor/sculptor/web/skills.py`
- **Issue:** Style guide bans `NamedTuple`; should be `FrozenModel`.
- **Bucket:** #3 (needed test changes — `skills_test` asserted via tuple equality).
- **Resolution:** Converted to `FrozenModel`; construction uses keyword args and
  the test assertions are instance comparisons. Commit *"Replace builtin
  exception + NamedTuple with domain types"*.

### 8. `SESSION_TOKEN` typed as plain `str` (secret)  ✅ RESOLVED
- **File:** `sculptor/sculptor/config/settings.py`
- **Issue:** Held the API session token as a plain `str`, so it could leak in
  logs/reprs; style guide says secrets use `pydantic.SecretStr`.
- **Bucket:** #5 (security; non-trivial fix).
- **Resolution:** Typed as `SecretStr | None`; unwrapped with `.get_secret_value()`
  at the two read sites (auth middleware comparison + set-session-token cookie),
  with the test fixtures updated to wrap the token. Commit *"Type SESSION_TOKEN as
  SecretStr"*.

---

## Tier 3 — Outstanding (deferred): persisted/serialized schema → needs `just generate-api` + frontend coordination

⏳ **Not done.** All are path-as-`str` or ID-as-`str` on `SerializableModel`s
whose TypeScript types are generated. Wire-compatible today; converting is
cross-stack churn.

| File | Field(s) | Notes |
|------|----------|-------|
| `config/custom_actions.py` | `id`, `group_id` as `str` | also persisted user-config w/ dual historical formats |
| `state/chat_state.py` | path fields as `str` | persisted + frontend-generated |
| `state/chat_state.py` | `tool_use_id: str` | `ToolUseID` exists; str-subclass → wire-safe (lower risk) |
| `state/messages.py` | `ChatInputUserMessage.files: list[str]` | frontend supplies Electron paths as strings |
| `telemetry/telemetry.py` | `sculptor_execution_instance_id: str` | served to frontend; str-subclass ID → lower risk |
| `web/data_types.py` | ~11 path fields | HTTP API shape |

**Recommendation:** batch into one deliberate "tighten persisted/wire domain
types" effort *with* the frontend, or leave. If you want a smaller first cut, the
ID-subclass ones (`tool_use_id`, telemetry id, custom-action ids) are lower-risk
since the JSON wire format is unchanged.

---

## Tier 4 — Leave as-is (correctly flagged, not actually defects)

No action — kept intentionally.

| File | Why leave it |
|------|--------------|
| `scripts/git_contributions.py` (`AuthorStats` dataclass) | Was a deliberately zero-dependency PEP 723 script; adding pydantic would break that. (The script itself was later removed as a zero-caller orphan in the dead-code commit.) |
| `interfaces/environments/base.py` & `agent_execution_environment.py` (`path: str`) | Intentional environment-vs-host path boundary (distinct from host `Path` via `to_host_path`/`to_environment_path`), shared protocol-wide. Not harmful primitive obsession. |
| `workspace_service/api.py` (`make_setup_state_provider(workspace_id: str)`) | The whole `setup_command_runner` subsystem threads `str` deliberately; caller does `str(...)` at the boundary. Low value to change alone. |

---

## Tier 5 — Outstanding (backlog): needs schema migration + test changes

### `alembic` downgrade asymmetry  ⏳ Not done
- **File:** `sculptor/sculptor/database/alembic/versions/811610e55bae_tasks_require_workspace.py`
- **Issue:** `upgrade()` injects `workspace_id` into `task_latest` rows;
  `downgrade()` drops the workspace tables but never removes the injected data →
  dangling reference after a down/up cycle.
- **Recommendation:** **Do not edit a released migration.** If it matters, fix
  forward in a new migration. Document as a known limitation.

### Non-deterministic message ordering  ⏳ Not done
- **File:** `sculptor/sculptor/services/data_model_service/sql_implementation.py`
- **Issue:** Standing FIXME — `get_messages_for_task` orders by `created_at` alone,
  non-deterministic on ties; needs a monotonic/auto-increment ordering key.
- **Bucket:** #2 (schema change + migration) + #3 (test changes).
- **Recommendation:** **Ticket it.** Add an ordering column + Alembic migration +
  update ordering tests.

---

## Remaining work

1. **Tier 3** — persisted/wire schema tightening, coordinated with the frontend.
2. **Tier 5** — alembic downgrade fix-forward + message-ordering key (both need a
   migration and test changes).
3. **Tier 4** — no action.
