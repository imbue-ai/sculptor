# Claude Code terminal agent installed out of the box — design

> **Status: implemented** on this branch (installer in
> `services/terminal_agent_registry/bundled.py`, env injection in
> `run_terminal_agent/v1.py`, parity TOML in
> `samples/terminal_agents/claude-code/`, packaging in
> `builder/build-sidecar.sh`, spec REQ-CLAUDE-1 amended).

Goal: the Claude Code registration is **installed automatically** into the
user's registrations directory (prod `~/.sculptor/terminal_agents/`, dev
`<repo>/.dev_sculptor/terminal_agents/`), as ordinary files the user can
**edit or delete** — no special "built-in" status in the registry. The
`samples/terminal_agents/claude-code/` files remain the single source the
installer copies from, and the example others build on. Also: bring the
launch command to parity with how Sculptor launches Claude in SDK mode.

## Part 1 — Install out of the box

1. **One-time installer at backend startup.** On startup, if the Claude Code
   registration has never been installed into this sculptor folder, write
   `claude-code.toml` + `claude-code-hooks.json` into
   `<sculptor_folder>/terminal_agents/` (creating the directory if needed)
   and record that the install happened (a sentinel — e.g. a dotfile in the
   directory or a `UserConfig` flag).

   - **Delete sticks:** "copy if file missing" alone would resurrect the
     registration on every restart after the user deletes it. The sentinel
     makes deletion permanent.
   - **Edits stick:** the installer never overwrites an existing file.
   - **Staleness is accepted:** once installed, the user owns the copy; a
     later app release with better flags does not silently rewrite it. (If
     wanted later: version-stamp the sentinel and offer a refresh.)
   - Because `get_sculptor_folder()` resolves per-mode, the same installer
     covers prod (`~/.sculptor`) and dev (`.dev_sculptor`) — dev gets it on
     the next `just start`.

2. **Machine-specific paths via injected env vars, not baked-in absolutes.**
   The installed TOML must reference the hooks file, the bundled plugin
   dirs, and the claude binary. Plugin dirs and the managed binary live
   inside the install (`_internal/` packaged, the repo checkout in dev) —
   paths that move on app update and, on Linux AppImage, on **every launch**
   (random mount point). Baking absolutes into a user-owned file breaks.

   Instead, the terminal-agent PTY already injects `SCULPT_*` env vars
   (`run_terminal_agent/v1.py` `extra_env`); add:

   - `SCULPT_PLUGINS_DIR` — the directory containing `sculptor-plugin`,
     `sculptor-workflow`, `sculptor-experimental` (today:
     `Path(sculptor.__file__).parent.parent`, same base `get_plugin_dirs()`
     uses).
   - `SCULPT_CLAUDE_BIN` — the managed Claude binary path
     (`Dependency.CLAUDE` via the dependency-management service), falling
     back to `claude` when unresolved.

   The launch command is typed into a login shell, so plain shell expansion
   resolves them at launch time:

   ```toml
   launch_command = "\"$SCULPT_CLAUDE_BIN\" --dangerously-skip-permissions --settings \"$HOME/.sculptor/terminal_agents/claude-code-hooks.json\" --plugin-dir \"$SCULPT_PLUGINS_DIR/sculptor-plugin\" --plugin-dir \"$SCULPT_PLUGINS_DIR/sculptor-workflow\" --plugin-dir \"$SCULPT_PLUGINS_DIR/sculptor-experimental\""
   ```

   (The hooks path is the one path that *is* stable — it sits next to the
   TOML — so the installer renders it absolute at install time; dev installs
   point it at `.dev_sculptor/...`. Alternatively inject
   `SCULPT_SCULPTOR_FOLDER` and keep the TOML fully static.)

   These env vars are useful to *any* registration author, which keeps this
   general rather than Claude-special.

3. **Packaging.** The sample files must ship with the app so the installer
   has a source: one `--add-data` line in `sculptor/builder/build-sidecar.sh`
   (script runs from `sculptor/`; `samples/` is at the repo root →
   `../samples/terminal_agents/claude-code:samples/terminal_agents/claude-code`),
   plus a small resolver that finds the source dir in both layouts
   (packaged `_internal/samples/...`, dev `<repo>/samples/...`).

4. **Spec + docs ripples.** REQ-CLAUDE-1 currently says the example is
   "enable/copy (not always-present in the menu)" and Non-Goals lists "an
   always-on built-in Claude Code menu entry" — amend both to "installed by
   default as a user-owned registration; user may edit or delete". Update
   the sample README (no manual copy needed; describes the installed files).

5. **Tests.**
   - Installer unit tests: installs on first start; never overwrites edited
     files; does not re-install after deletion (sentinel honored); renders
     the hooks path for the destination folder.
   - Menu integration test: a fresh instance shows "Claude Code" in the `+`
     menu and the new-workspace picker with no setup.
   - Existing-test ripple: every integration-test instance has a fresh
     sculptor folder, so the entry now appears in all menus — audit tests
     that assert registered-entry absence (they key on their own fake ids,
     so expected churn is minimal).
   - Real-Claude e2e: its `_install_sample` overwrite becomes the
     "user edited their copy" path; re-run it (also covers any new startup
     dialog — see Part 2).

## Part 2 — launch command parity with SDK mode

SDK mode (`get_claude_command`, `process_manager_utils.py:45-110`) runs:

```
env IS_SANDBOX=1 <managed-binary> --dangerously-skip-permissions
  --permission-prompt-tool stdio --output-format=stream-json --verbose
  --input-format stream-json --include-hook-events
  --mcp-config <in-process sdk server>
  --disallowed-tools AskUserQuestion,ExitPlanMode
  [--include-partial-messages] [--resume <id>]
  [--append-system-prompt <sculptor prompt>] [--model <m>]
  --plugin-dir <sculptor-plugin> --plugin-dir <sculptor-workflow>
  --plugin-dir <sculptor-experimental>
  [--settings '{"fastMode": true}'] [--effort <e>]
```

### Carry over to the TUI registration

- `--dangerously-skip-permissions`.
- `--plugin-dir` for **all three** bundled plugins (`sculptor-plugin`,
  `sculptor-workflow`, `sculptor-experimental`) — `get_plugin_dirs()` ships
  all three, not just sculptor-workflow.
- **The managed Claude binary** (via `SCULPT_CLAUDE_BIN`), not bare `claude`
  from PATH: a user who never installed Claude globally gets "command not
  found", and PATH claude can skew versions vs SDK agents. The managed
  binary shares `~/.claude` auth, so subscription billing still works.
- **The resume template must mirror every flag** — a flag added only to
  `launch_command` is otherwise silently missing after restart-resume.
  Render both commands from the same base.

### Deliberately NOT carried over (comment this in the TOML)

- `--output-format/--input-format stream-json`, `--verbose`,
  `--include-hook-events`, `--include-partial-messages`,
  `--permission-prompt-tool stdio` — SDK wire protocol; breaks the
  interactive TUI.
- `--mcp-config` (in-process SDK server) and
  `--disallowed-tools AskUserQuestion,ExitPlanMode` — these exist to replace
  TUI affordances with Sculptor's chat UI; in the TUI the native ones are
  the point.
- `--append-system-prompt` — the Sculptor system prompt is SDK-harness
  specific (AUQ/MCP/plan-mode plumbing) and wrong for the TUI.
- `--model`, `--effort`, fast-mode `--settings` — the TUI has its own
  pickers.

### IS_SANDBOX — investigated, NOT carried over

What `IS_SANDBOX=1` actually does in the Claude binary (verified against
claude 2.1.175 by extracting the bundled JS):

1. **Root escape hatch:** `--dangerously-skip-permissions` as root
   (`getuid()===0`, not bubblewrap) without `IS_SANDBOX=1` exits 1 with
   "cannot be used with root/sudo privileges for security reasons".
2. **Containment heuristic:** counts as "is sandboxed" in the
   contained-no-internet detection (`(isDocker || isBubblewrap ||
   IS_SANDBOX==="1") && !hasInternet`).
3. **529-overload retries:** with it set, claude keeps retrying repeated
   API-overload errors instead of surfacing them.
4. It does **NOT** suppress the bypass-permissions disclaimer dialog —
   that is `skipDangerousModePermissionPrompt` (any settings scope,
   including `--settings`) or a recorded `bypassPermissionsModeAccepted`.

History: the introducing commit predates the clean-history epoch
(`git log -S IS_SANDBOX` bottoms out at the epoch commit), but the why is
clear from (1): Sculptor's agents originally ran in containerized sandboxes
**as root**, where claude refuses the flag without it. Today
`EnvironmentTypes = LocalEnvironment` only — agents run as the login user.

Decision (user-confirmed): **omit it from the TOML** (terminal agents run
as the non-root login user; none of the three behaviors is needed) and
**keep it in the SDK call sites** (`process_manager_utils.py:64`,
`btw_process_manager.py:67`) — one env var, protects root-on-Linux
installs, keeps resilient overload retries.

### Details easy to miss

- `--dangerously-skip-permissions` adds a first-run **disclaimer dialog**
  in the TUI. Decision (user-confirmed): skip it by adding
  `"skipDangerousModePermissionPrompt": true` to the hooks/settings JSON we
  already pass via `--settings` (verified: the flag-settings scope counts) —
  smooth first run, mirrors SDK mode's no-prompt behavior.
- Env parity is already adequate: the PTY injects project env vars +
  `SCULPT_*`, and the login shell carries the user's own `CLAUDE_*` vars.
- TOML escaping: the launch command now contains quotes — use a TOML
  literal string (`'...'`) or escaped basic string carefully; the loader's
  round-trip test pins this.
