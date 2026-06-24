# REQ-by-REQ trace — TypeScript backend (Task 9.5)

Each measurable / contractual `requirements.md` bar mapped to the TS backend
module that realizes it and the targeted test that pins it. The broad behavioral
oracle is the Python integration/scenario suite (~446 scenarios) run unchanged
against the TS backend under the `SCULPTOR_BACKEND=ts` env gate (RW-VERIFY-1,
Task 1.6); this table closes the numeric/contractual bars that suite does not
exhaustively pin. Paths are under `sculptor/backend/` unless noted.

## Performance / responsiveness (REQ-NFR)

| Bar | Module | Test |
|---|---|---|
| REQ-NFR-001 — snapshot-then-incremental-delta streaming | `src/projection/snapshot.ts`, `src/projection/delta.ts`, `src/routes/stream_ws.ts` | `src/routes/stream_ws.test.ts`, `src/projection/*.test.ts` |
| REQ-NFR-010 — many concurrent agents, independent progress | `src/runner/runner.ts`, `src/runner/concurrency.ts` | `src/runner/runner.test.ts` |
| REQ-NFR-011 — PR/CI pool **4 workers + 1.5 s global spacing** | `src/services/pr_polling/pool.ts` (`BoundedPool`, `PollSpacingThrottle`) | `src/services/pr_polling/pr_polling.test.ts` ("max 4 workers", "global 1.5s spacing") |
| REQ-NFR-020 — quit/crash + reopen restores everything | `src/runner/runner.ts` `resuperviseOnStartup`; persistence in `src/db/` | `src/runner/runner.test.ts`; migration resume `src/migrate/migrate.seed_verify.test.ts` |
| REQ-NFR-021 — errored agent surfaces + offers restore | `src/services/agent.ts` `restore`; `src/routes/agents.ts` restore route | agents route tests |
| REQ-NFR-031 — DB **WAL + 15 s busy timeout** | `src/db/connection.ts` (`openDatabase` PRAGMAs) | covered by every DB-backed route/integration test opening via `openDatabase` |
| REQ-NFR-040 — backend-readiness **60 s** timeout + printed-URL parse | `src/index.ts` (ready line + URL), `sculptor/frontend/src/electron/main.ts` `waitForBackend` | Electron-mode integration suite; sidecar boot verified in Task 9.1 |
| REQ-NFR-051 — max upload **20 MB** | `src/routes/uploads.ts` (`MAX_UPLOAD_SIZE_BYTES`, 413) | `src/routes/misc.test.ts` ("rejects an oversize upload with 413") |
| REQ-NFR-060 — PR/CI poll **interval 30 s, floor 10 s** | `src/services/pr_polling/pool.ts` `computePollDelaySeconds` | `src/services/pr_polling/pr_polling.test.ts` ("floor, closed multiplier, terminal backoff") |
| REQ-NFR-061 — local/remote-branch poll **3 s** | `src/services/repo_polling/manager.ts` (`WORKSPACE_BRANCH_POLL_SECONDS`) | `src/services/repo_polling/repo_polling.test.ts` |
| REQ-NFR-062 — CI babysitter **off by default, retry cap 3** | `src/services/ci_babysitter/coordinator.ts` | `src/services/ci_babysitter/ci_babysitter.test.ts` ("off by default", "retries up to the cap of 3") |
| REQ-NFR-070 — new-agent model = most-recently-used | `src/services/agent.ts` create (default model resolution) | agents route tests |

## Integrations (REQ-INT)

| Bar | Module | Test |
|---|---|---|
| REQ-INT-001 — provider from `origin` (SSH+HTTPS) → gh/glab | `src/services/pr_polling/provider.ts` | `src/services/pr_polling/pr_polling.test.ts` ("recognizes GitHub and GitLab over SSH and HTTPS") |
| REQ-INT-002 — PR/CI ops via provider CLI | `src/services/pr_polling/status.ts` | `src/services/pr_polling/pr_polling.test.ts` (`fetchPrStatus` cases) |
| REQ-INT-003 — failure taxonomy distinct (cli_missing / not_authenticated / rate_limited / network_error / no_access) | `src/services/pr_polling/cli_status.ts` `classifyCliError` | `src/services/pr_polling/pr_polling.test.ts` ("taxonomy stays distinct", cli_missing/rate_limited cases) |
| REQ-INT-021 — Claude as long-lived stream-json process | `src/harness/claude/harness.ts` | `src/harness/claude/harness.test.ts` |
| REQ-INT-022 — Pi `--mode rpc` + session-dir/id | `src/harness/pi/harness.ts` | `src/harness/pi/harness.test.ts` |
| REQ-INT-023 — missing CLI binary raises a surfaced error | `src/services/dependencies.ts` (managed-binary discovery) | dependencies service test |
| REQ-INT-030 — terminal-agent TOML registrations, **re-read on demand** | `src/services/terminal_agent_registry/registry.ts` `listRegistrations` | `src/services/terminal_agent_registry/registry.test.ts` ("re-reads on demand") |
| REQ-INT-031 — **literal** placeholder substitution (not `.format()`) | `src/services/terminal_agent_registry/registry.ts` `renderTerminalCommand` | `src/services/terminal_agent_registry/registry.test.ts` ("LITERAL replacement", braces/percent pass through) |
| REQ-INT-040 — `sculpt` reaches `http://localhost:<port>` | session-token + port (`src/config/port.ts`, `src/auth/session_token.ts`) | behavioral: `test_sculpt_cli.py` |
| REQ-INT-041 — CLI client generated from backend OpenAPI | `src/openapi.ts` (overlay) + justfile `generate-sculpt-client` | regenerated sculpt client byte-identical (Task 9.4); behavioral `test_sculpt_cli.py` |
| REQ-INT-050 — `.env` **per-repo over global** precedence | `src/services/env_injection/env.ts` `resolveEnv` | `src/services/env_injection/env.test.ts` ("per-repo over global") |

## Security (REQ-SEC)

| Bar | Module | Test |
|---|---|---|
| REQ-SEC-002 — env surface is **names only** (no values) | `src/services/env_injection/env.ts` `projectEnvVarNames`; `src/routes/config.ts` env-var-names | `src/services/env_injection/env.test.ts` ("names only"); `src/routes/config.test.ts` |
| REQ-SEC-003 — macOS artifact signed/notarized | `sculptor/backend/scripts/build-sidecar.sh` (codesign node + .node when `SIGN_IDENTITY`), `sculptor/builder/build-sidecar.sh` | build/CI env (signing creds) |
| REQ-SEC-010 — telemetry **consent-gated** + private-content masking | `src/telemetry/posthog.ts` (`capture` re-checks consent; `maskProperties`) | `src/telemetry/posthog.test.ts` ("emits nothing when consent is not granted", masking) |

## Compatibility (REQ-COMPAT)

| Bar | Module | Test |
|---|---|---|
| REQ-COMPAT-001/002 — macOS-arm64 + linux-x64 builds | `sculptor/backend/scripts/build-sidecar.sh` (`SIDECAR_TARGET` macos-arm64/linux-x64), `openhost.Dockerfile` (linux-x64) | sidecar boot verified (Task 9.1); image build in CI |
| REQ-COMPAT-020 — Claude version window (recommended 2.1.170; 2.1.101 blocked) | `src/services/dependencies.ts` (`isVersionInRange`, blocked-version list) | dependencies service test |
| REQ-COMPAT-022 — Pi pinned 0.78.0 | `src/services/dependencies.ts` (pi pin) | dependencies service test |

## Data / migration (REQ-DATA, RW-DATA)

| Bar | Module | Test |
|---|---|---|
| REQ-DATA-001/002 — single Sculptor folder + internal layout | `src/config/sculptor_folder.ts` | folder-bootstrap test; `test_migration.py` (bootstrap) |
| REQ-DATA-004 — persisted entities (UserSettings/Project/Workspace/Task/messages/Notification) | `src/db/schema/*` | schema + repo tests |
| REQ-DATA-011 — migrations run automatically at startup | `src/db/migrate.ts` `runMigrations` (drizzle) | every integration boot |
| RW-DATA-3/5/6/8 — one-time DB migration: all entities, IDs verbatim, on-disk layout preserved, fail-loud forward-only | `src/migrate/{read_old_db,transform,run,index}.ts` | `src/migrate/migrate.seed_verify.test.ts` (six entities, `tsk_` preserved, outcome→run_state, session carried, config.toml untouched, fail-loud) |
| REQ-DATA-021 — (historical) folder-migration helper removed; DB-only in-place migration | `src/migrate/` | see RW-DATA row |

## Wire / API / deploy (RW-API, RW-DEPLOY)

| Bar | Module | Test |
|---|---|---|
| RW-API-3 — camelCase wire shapes | REST routes (camelCase) + `src/projection/to_wire.ts` (stream boundary camelizer) | `src/projection/to_wire.test.ts`; route tests |
| RW-API-4/5 — one OpenAPI regenerates both clients, no manual adaptation | `src/openapi.ts` (overlay), justfile/frontend codegen | frontend client 0 tsc errors + sculpt client byte-identical (Task 9.4) |
| RW-DEPLOY-1/2/3 — Node sidecar packaging + same launch UX + self-host serves UI | `sculptor/backend/scripts/build-sidecar.sh`, `sculptor/frontend/src/electron/main.ts`, `openhost.Dockerfile` | sidecar boot + `/api/v1/health` verified (Task 9.1); Electron-mode + image in CI |

## Notes

- The full integration/scenario suite under `SCULPTOR_BACKEND=ts` is the
  RW-VERIFY-1 oracle and runs in CI/the harness (electron + real-claude +
  hours); known-flaky jobs (`browser_panel` electron, PTY under `-n 8`
  parallelism, offload base-image cache-miss) pass on retry — re-run, don't
  recode. This trace is the close-out for the numeric/contractual bars; per
  Task 9.5 it is the precondition for the Task 9.6 deletion (Python stays as a
  fallback until green is confirmed under the env gate).
