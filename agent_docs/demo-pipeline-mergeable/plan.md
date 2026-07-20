# Plan: Make the marketing screenshot pipeline mergeable (single PR)

Branch: `bryden/orange-newt`. Goal: remove the sculptor-guy scene, replace every
`DEMO-SCAFFOLD` with either a real bug fix or legitimate harness/demo
infrastructure, rehome the pipeline as repeatable dev tooling, and ship the UI
polish already in the tree. No product feature flags: all demo-specific behavior
lives in the test harness and demo tooling, configured through the existing
`TESTING` settings channel and process environment.

## WS0 — Deletions

- `marketing/sculptor-guy/` (svgs, plugin copy, index.html, README)
- `marketing/seed/seed_sculpty.py`, `marketing/shots/sculpty_frame.py`
- `marketing/NIGHTSHIFT.md` (one-off results log)
- Revert the `themeBuilder.ts` DEMO-SCAFFOLD comment (appearance flips stay a
  manual harness concern).

## WS1 — Ship the standalone UI work (already in tree)

StatusDot redesign (+ new stories under `src/stories/custom/statusDot/`),
storybook ESM `__dirname` fix, sidebar polish (gray-1 rail, 30px rows, active
weights, repo-name type), "Pi"/"Terminal Agent" labels + picker reorder.
No code changes needed — verify (vitest, storybook screenshots) and commit.
StatusDot touches SectionHeader/TabPill ⇒ run the panel/section frontend
integration suites.

## WS-pre — Sequencing: commit polish, drop scaffolds, catch up to main

The scaffolds are all *uncommitted* working-tree edits, so none of them ever
need to enter history. Order:

1. Commit WS1 (UI polish files only).
2. Restore the scaffold-edited files to HEAD (`prStatus.ts`, `modelConstants.ts`,
   `dependenciesStatus.ts`, `app.py`, `fake_claude_commands.py`,
   `themeBuilder.ts`) — each replacement below re-implements properly.
   `auth.py` keeps its edit (comment reworded in WS8).
3. Merge `origin/main` (branch is ~216 commits behind; brings the merged 422
   fix, PR #363). Resolve conflicts, especially around the WS1 UI files.
4. Implement the workstreams below on top.

## WS2 — Bug fix: settings singleton (removes the app.py gate hack)

Root cause (verified): `get_settings()` in `sculptor/sculptor/web/middleware.py:84`
constructs a fresh `SculptorSettings()` per request, re-parsing `os.environ`
every time, violating the class's own "does not change during runtime" contract
(`config/settings.py:30-35`). No in-repo mutation site was found for
`TESTING__INTEGRATION_ENABLED`, but per-request re-reads make the gate fragile.

A prior TDD workspace investigated the same symptom, could NOT reproduce any
actual env mutation, and filed **SCU-1809** proposing the gate read
startup-frozen settings. This workstream implements/closes SCU-1809.

- Add `@lru_cache` to `get_settings()` (test overrides via
  `APP.dependency_overrides` are unaffected). Broader than SCU-1809's
  gate-local proposal: hardens every `Depends(get_settings)` consumer.
- Revert the `_demo_allow_test_models` scaffold in `web/app.py` (~:562-570).
- Unit test: `get_settings() is get_settings()`.

## WS3 — 422 client crash: ALREADY FIXED on main (PR #363, merged)

Root cause was verified (stock `openapi-python-client` parser iterating a
string detail), but **SCU-1810 / PR #363 already fixed it on main** by widening
`HTTPValidationError.detail` to `str | list[ValidationError]` in
`generate_json_schema.py` — survives regeneration, covers both the sculpt and
frontend clients, and ships with unit tests.

- The parser fix arrives via the WS-pre merge of origin/main.
- Drop the raw-httpx bypass in the demo `harness_client` and use the generated
  parsers (regenerate the client once on the merged branch).
- ALSO in this PR (Bryden's call): migrate the 10 hand-raised string/dict-detail
  422s in `web/app.py` to honest status codes — 400 for bad input
  (`:548, :569, :606, :2024, :2029, :2143, :2930, :3794, :4787` — line numbers
  pre-merge, re-locate after), 409 for the dict-detail "no setup command
  configured" (`:898`, matches sibling 409 at `:900`). Frontend verified safe:
  `apiClient.ts` discriminates on detail shape, not status. Update any tests
  asserting 422 from these endpoints. Leave the 9 list-shaped 422 sites alone
  (they are genuine validation-shaped responses).

## WS4 — Bug fix: harness provisions pi (removes the dependenciesStatus hack)

Root cause (verified): `PI_VERSION_RANGE` is an exact pin (`0.80.2`); pytest
fixtures plant an INSTALLED_STUB pi reporting exactly that, but
`ManualTestHarness` provisions nothing — it resolves whatever `pi` is on the
developer's PATH, which correctly reports out-of-range. Not a race; the first
snapshot is computed synchronously and complete.

- In `manual_test_harness.py`: plant the stub via
  `dependency_stubs.create_disabled_dependency_stub(stub_dir, "pi", INSTALLED_STUB)`
  and pin `dependency_paths=DependencyPaths(pi=<stub>)` inside
  `_make_test_user_config()` (persisted by `_populate_sculptor_folder`).
- Revert the `isPiAvailableAtom` scaffold in
  `frontend/src/common/state/atoms/dependenciesStatus.ts`.

## WS5 — Display-name override for testing models (removes the modelConstants hack)

Rides the existing settings stream — zero new transport
(`SculptorSettings` → `stream_everything` → `UserUpdate.settings` →
`sculptorSettingsAtom`).

- Backend: `TestingConfig` (config/settings.py:23) gains
  `FAKE_MODEL_DISPLAY_NAME: str | None = None`. Semantics: when set, testing
  models render with this label AND are hidden from the model picker. Env:
  `TESTING__FAKE_MODEL_DISPLAY_NAME` (via `env_nested_delimiter="__"`).
- Frontend: revert modelConstants scaffold (restore "Fake Claude"/"Fake Claude 2"
  and `TESTING_ONLY_MODELS = [FAKE_CLAUDE, FAKE_CLAUDE_2]`). New selector atom
  beside `isIntegrationTestingEnabledAtom` in `sculptorSettings.ts`. Apply the
  override at the two render sites — `ModelSelector.tsx:69` (trigger short name)
  and `ModelSelectOptions.tsx:67` (option long name) — and exclude
  `TESTING_ONLY_MODELS` from `getClaudeModelList` when the override is set.
  Keep `modelConstants.ts` pure (no atom imports); pass the override in.
- `just generate-api` for the TS `TestingConfig` type.
- Demo harness sets `TESTING__FAKE_MODEL_DISPLAY_NAME=Fable`; the integration
  harness (`server_utils.py:185`) stays untouched, so all literal
  "Fake Claude" label tests keep passing. Leave the existing
  `SCULPTOR_MANUAL_TEST_HIDE_FAKE_MODELS` flow (update-help-docs) alone.
- Vitest unit for label + list override.

## WS6 — FakeClaude ask-question timeout as directive arg

`fake_claude_commands.py handle_ask_user_question`:
`timeout_seconds=float(args.get("timeout_seconds", 180.0))` — remove the
hardcoded 86400; the demo manifest passes `timeout_seconds=86400` on the
amber-state turn.

## WS7 — gh shim (removes the prStatus.ts scaffold entirely)

Verified contract: PR polling only runs `git rev-parse --abbrev-ref HEAD`,
`git remote get-url origin`, and two `gh api graphql` shapes (batched
`search(` query with `rateLimit`, per-workspace `repository(owner:` query with
`-f branch=<branch>`). No `gh auth` anywhere in the polling path. PATH flows
launcher env → backend subprocess → gh subprocess with no scrubbing.

- Revert `prStatus.ts` to the plain primitive atomFamily.
- New executable `gh` shim (python) in the demo tooling:
  - dispatch on query body: `search(` → search envelope (all open fixtures as
    nodes with `repository.nameWithOwner` + `headRefName`, healthy
    `rateLimit` {cost:1, remaining:4999, limit:5000, resetAt far future},
    `pageInfo.hasNextPage:false`); `repository(owner:` → repository envelope for
    the branch parsed from argv.
  - fixtures from JSON file via env `SCULPTOR_DEMO_GH_FIXTURES`
    (branch → number/title/url/state/baseRefName/checks/reviews).
  - always exit 0; never print rate-limit-ish text to stderr (would trigger a
    60s global cooldown).
  - open PR ⇒ in search response; merged PR ⇒ absent from search (it's
    state:open) + MERGED node in the repository response (fallback path).
- Harness launch prepends the shim dir to PATH.
- Seeded repos: `git remote set-url origin https://github.com/<owner>/<repo>.git`
  so `_is_github_url` passes and the search index keys
  (nameWithOwner, headRefName) match exactly.
- Optional: tiny pytest feeding both query bodies through the shim and asserting
  the envelopes parse.

## WS8 — Rehome + de-hardcode the pipeline

- Stays top-level in `marketing/` (Bryden's call — no package rehome). Exclude
  the directory from the repo tooling that would otherwise sweep it: the
  `just format`/`just check` targets, pyright/eslint includes, and the ratchet
  configs, as applicable (verify which actually match it and add ignores only
  there). Code still hand-matches house style (~100 cols, like tools/sculpt).
  Contents: manifest.py, seed_all.py, seed_hero.py, fakeclaude.py,
  harness_client.py, induce_state.py, gh_shim/, harness.py, README.md, and a
  shots helper (control.sh or shots.py).
- Repos: clone into a scratch dir (/tmp or ~/.cache/sculptor-demo), fresh clone
  per seed (local clones hardlink; cheap) — kills `free_branch()` and all
  `demo/*` pollution of real checkouts. Sculptor's clone source defaults to the
  repo root the tool runs from; openhost/mngr configurable
  (env `SCULPTOR_DEMO_REPO_<NAME>=<path>` or `--repo name=path`), gracefully
  skipped when absent. Set the fake github origin per WS7.
- harness_client: screenshots/ports dir from env/CLI
  (`SCULPTOR_DEMO_DIR` / `--screenshots-dir`), keep `HARNESS_BACKEND_PORT`
  escape hatch; switch to generated parsers post-WS3.
- ensure_harness.sh → `demo/harness.py`: idempotent ensure/boot of
  manual_test_server with PATH=shim-dir + `TESTING__FAKE_MODEL_DISPLAY_NAME=Fable`
  + `SCULPTOR_DEMO_GH_FIXTURES=<path>`; writes port files.
- Keep the neutral git identity (Sculptor Demo <demo@imbue.com>).
- `just demo-seed` recipe for discoverability.
- README rewritten: no user paths, no scaffold table (gone), documents the knobs.
- `tools/sculpt/auth.py` fake/fake2 aliases: keep, reword comment as permanent
  test-tooling doc (backend-gated by the integration flag) — no DEMO-SCAFFOLD.

## Verification

- `just format` / `just check` / `just test-unit` / `just ratchets` at commit
  points (not preemptively).
- Unit: settings singleton; 422→400 endpoint assertions; modelConstants override
  vitest; shim envelope pytest.
- Integration (offload): test_model_capability_gating, test_task_page_chatting,
  test_fast_mode_persistence, regression model-selection/MRU tests,
  test_pi_capability_gating, panel/section suites (StatusDot callers).
- End-to-end: boot harness, seed, capture the multi-repo sidebar (PR pills via
  real polling + shim), Fable label, amber waiting state; post screenshots
  inline.

## Commit plan (stacked, no amends; public-repo-safe messages)

1. UI polish (StatusDot + stories, storybook fix, sidebar, labels)
2. Merge origin/main (catch up ~216 commits; brings the 422 parser fix)
3. Settings singleton fix (closes SCU-1809)
4. 422 → 400/409 migration (the 10 hand-raised sites)
5. Harness pi provisioning
6. Testing-model display-name override (+ `just generate-api`)
7. FakeClaude ask-timeout arg
8. Demo pipeline overhaul in `marketing/` (/tmp clones, gh shim, config knobs,
   tooling excludes); delete sculptor-guy + all remaining scaffolds

## Decisions (resolved 2026-07-14)

1. Tooling home: top-level `marketing/`, excluded from format/check/ratchets
   where those would sweep it. (Bryden: no package rehome.)
2. Fake origin owner: `imbue-ai/<repo>`. The origin URL must exist and look
   github-shaped at all — `_is_github_url(origin)` gates whether PR polling
   runs, and fresh /tmp clones of local repos otherwise have a filesystem-path
   origin, so no polling and no pill. The owner string also keys the search
   index match (`repository.nameWithOwner` ↔ origin owner/repo), so the shim
   fixtures and the remote must agree. The value itself is near-invisible
   (pr URL only on click).
3. Override semantics: one field — `FAKE_MODEL_DISPLAY_NAME` set ⇒ relabel +
   hide from picker.
4. 422→400/409 migration: in this PR.
