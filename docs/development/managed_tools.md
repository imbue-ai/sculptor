# Managed tools are overrides inside Sculptor

Status: **decided** on 2026-11-23. It binds every tool Sculptor manages, which
today means Claude Code, pi and jj. The code does not follow it everywhere yet;
[Where the code differs](#where-the-code-differs) lists the gaps known when it
was written.

## The decision

A managed tool is a program that Sculptor downloads, pins to a version it has
tested, and verifies against a checksum (`ManagedTool` in
`sculptor/sculptor/services/managed_tools.py`). Each managed tool has two modes
in Settings:

- **Managed:** Sculptor uses the copy it ships.
- **Custom:** Sculptor uses a copy the user names, by absolute path or by
  command name.

Choosing Managed tells Sculptor: keep working with what you ship. A user picks
it for one of three reasons:

- They do not have the tool installed.
- They do not want to keep their own copy in step with Sculptor.
- They keep a different version on purpose, for work outside Sculptor.

The same four rules serve all three:

1. **Inside Sculptor, the managed copy is the tool.** Sculptor's own calls, its
   agents, and every process it launches run the managed copy. That covers
   chat agents, terminal agents, workspace terminals, setup commands and any
   other command Sculptor runs for the user, in every kind of workspace. A
   copy the user installed never shadows the managed one, whatever the user's
   shell profile puts first on PATH.
2. **Outside Sculptor, the managed copy is invisible.** Sculptor never puts a
   managed copy on the user's own PATH, never edits their shell profile, and
   never installs into a system location. A user who wants Sculptor's copy
   elsewhere runs it by the absolute path that Settings shows. Doing so is a
   deliberate step, never a default.
3. **Managed never falls back.** When the managed copy is missing or broken,
   the tool is not installed as far as Sculptor is concerned: readiness says
   so and offers to install or repair it. Sculptor never substitutes a copy it
   finds on PATH, because that would run an untested version under the
   managed label.
4. **Custom is the way to opt out.** Sculptor checks the named copy's version
   against the range it supports, then uses that copy wherever it would have
   used the managed one. Rule 1 holds with the user's copy in its place, so
   Sculptor and everything it launches still agree on one copy. Custom
   changes nothing outside Sculptor either.

## How rule 1 is enforced, and where it stops

Sculptor's own calls run a managed tool by absolute path, never by name.

For a process it launches, Sculptor puts the directory of the copy in effect
first on PATH when the process starts. A login shell's profile runs after that
and can reorder PATH, through macOS `path_helper`, `~/.cargo/env`, or a version
manager's activation script. So Sculptor puts the directory first again after
the profile has run. Terminal agents (`with_path_prefixes_first`) and the setup
command (`_reapply_path_prefixes`) already do this for jj.

The guarantee is that, in any process Sculptor launches, looking the tool's
name up on PATH finds the copy Sculptor resolved. It does not override an
explicit choice the user makes inside a shell:

- an absolute path, such as `~/.cargo/bin/jj`;
- an alias or shell function that names another copy;
- a per-directory version manager (direnv, mise, asdf) that rewrites PATH
  after the shell has started.

A probe can check the guarantee: it starts a shell the way each launch form
does and asks which copy the name resolves to. A different answer is a bug in
Sculptor. Sculptor fixes it rather than asking the user to change their
profile.

## What is shared

The binaries are separate. The user's identity and data are not.

- **Identity, credentials and preferences belong to the user, and are shared
  on purpose.** A managed jj records changes under the user's jj identity, and
  a managed Claude Code uses the user's Claude configuration directory.
  - When one of the user's settings would break Sculptor's own use of a tool,
    Sculptor overrides that setting in the processes it launches, and only
    there.
  - It uses the tool's own override mechanism, an environment variable or a
    flag, as `JJ_EDITOR=false` does for chat agents. It never edits the user's
    files.
- **Files that a tool writes into the user's repositories are also read by
  the copy the user runs outside Sculptor.** A managed jj newer than the
  user's own copy can leave a repository that their copy cannot read.
  - Sculptor cannot fix the user's copy, and does not block its own work over
    it.
  - It names the user's copy and the version needed. It says so before the
    first write that would expose that copy to the newer format, such as
    colocating a repository.
- **A managed tool's prerequisites are declared and checked.** A managed tool
  can run host programs that Sculptor does not manage: jj runs git to fetch
  and push. Each such prerequisite has a minimum version that readiness checks
  (jj's `UNSUPPORTED_GIT`). The tested combination is the managed version
  with its prerequisites at or above their minimums.

## Consequences

- **Each tool has one mode per Sculptor installation, not one per
  repository.**
  - A repository that pins its own version of a tool, for example in
    `mise.toml` or `.tool-versions`, is overridden inside Sculptor while that
    tool is Managed.
  - That is right for tools Sculptor itself depends on, and wrong for a
    project's own toolchain, so Sculptor manages only the first kind.
  - A project that needs a different version of a managed tool needs Custom.
- **Agent guidance for a managed tool is written for the managed version.**
  This covers skills and system-prompt rules. It holds because the managed
  version is what agents run. The vendored jj skill names the version it was
  tested with, and that version must stay inside the supported range.
- **Managed versions change only with Sculptor releases.** Each is pinned,
  with checksums baked in at the version bump (`ReleasePin`). Upgrading
  Sculptor can raise a tool's version. Downgrading Sculptor can meet
  repositories written by a newer version.
- **The same command can give different answers inside and outside
  Sculptor.** `jj --version` in a workspace terminal shows the managed
  version, while the user's own terminal shows theirs. That is intended.
- **`sculpt` follows the same idea.** Sculptor ships it rather than
  downloading it. `get_sculpt_bin_dir` gives launched processes a directory
  holding only this installation's `sculpt`, so that shell startup scripts
  which demote a development virtualenv cannot put another `sculpt` first.

## Adding a managed tool

Manage a tool only when Sculptor depends on it to do its own work and will
test the pinned version. Before the tool ships:

- Sculptor's own calls resolve it to an absolute path through
  `resolve_binary_path`. Launched processes get its directory first on PATH,
  put first again after the profile has run.
- What it reads from the user (configuration, credentials) is known, and so
  is what it writes into places the user owns. The environment variables
  that keep everything else separate are known too. For example, a managed
  TeX distribution would need its `TEXMFHOME` and cache variables pointed at
  Sculptor's own tree, or the user's local packages would leak in.
- Its host prerequisites have minimum versions that readiness checks.
- Its agent guidance names the version it was written for.

## Where the code differs

These gaps were found while writing this decision. The list is not
exhaustive; a review of the codebase against this decision follows it.

- **Managed pi and jj fall back to a copy on PATH** when no managed copy has
  been downloaded. See `_resolve_optional_tool_path` in
  `sculptor/sculptor/services/dependency_management_service.py`, and the
  `DependencyPaths` docstring in `sculptor/sculptor/config/user_config.py`.
  Managed Claude Code already never falls back.
- **A workspace terminal the user opens runs whatever their profile puts
  first.**
  - For jj, an out-of-range copy found there is the `SHADOWED` readiness
    blocker, which asks the user to change their machine.
  - Under this decision, the terminal puts Sculptor's jj first again after
    the profile has run, as terminal agents already do.
  - A jj outside Sculptor that is too old becomes a warning, as described in
    [What is shared](#what-is-shared). The jj design records this as decision
    20 in [jujutsu.md](jujutsu.md).
- **jj's directory (`jj-bin`) goes on PATH only in jj workspaces**, so a git
  workspace's terminal runs the user's own jj.

## Open questions

- Existing users whose Managed pi or jj currently runs a copy found on PATH:
  should Sculptor switch them to Custom with that copy, or ask them?
- Should a source checkout treat the pinned jj that `just install-jj` places
  in the virtualenv as its managed copy, the way `get_sculpt_bin_dir` uses the
  virtualenv's `sculpt`?
