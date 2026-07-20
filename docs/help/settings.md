# Settings

Open Settings with `Cmd+,`, or click **Settings** at the bottom of the
sidebar. Settings opens in its own tab. The sections:

- **General** — theme (Light / Dark / System) and software updates: release
  channel (Stable or Latest), check for updates, and install (desktop app
  only).
- **Extensions** — manage [extensions](extensions.md): toggle bundled and
  installed extensions, and control whether agents may load extensions into
  your UI.
- **Dependencies** — the external tools Sculptor uses: the Claude CLI
  (managed by Sculptor or a custom binary), git, and the GitHub CLI.

Under **Harnesses**:

- **Claude** — defaults for new Claude agents: model, fast mode, and effort
  level.
- **Pi** — the pi harness: managed or custom binary, the API-key environment
  variables passed to it, and LLM provider connections.

Under **Interface**:

- **Keybindings** — view and customize keyboard shortcuts, with conflict
  detection and reset-to-defaults.
- **Theme builder** — experimental fine-grained appearance controls: fonts,
  code theme, accent and status colors, radius, and scaling.

Under **Project**:

- **Repositories** — add or remove repos, and set each repo's workspace setup
  command and branch-naming pattern.
- **Git** — the pull-request creation prompt, PR status polling, default
  target branch, default branch-naming pattern, and the branch-deletion
  policy for removed workspaces.
- **CI** — the [CI Babysitter](ci_babysitter.md): when enabled, Sculptor
  watches open PRs and asks an agent to fix CI failures and merge conflicts,
  with a configurable agent, retry cap, and prompts.
- **File browser** — line wrapping, the default diff view (unified vs.
  split), and the commit prompt.
- **Environment variables** — the global (`~/.sculptor/.env`) and per-repo
  (`.sculptor/.env`) files, and whether they override existing shell
  variables.

And after those:

- **Privacy** — your account email and the telemetry toggle.
- **Experimental** — features still in development, including workspace-mode
  toggles and, on the desktop app, the custom backend command (see
  [Container Backend](experimental/container_backend.md)).
- **Actions** — manage your saved prompts (reusable one-click actions) and
  groups, with import and export.
