# pi Skills — How Sculptor's Skills Map onto `--skill`

How Sculptor points pi at the same skills the slash picker offers, and the four
mapping rules that make pi's skill model line up with Sculptor's.

> Source of truth: `_build_skill_launch_args`, `_synthesize_command_skills`,
> `_rewrite_skill_invocation`, and `_render_synthesized_skill` in
> `sculptor/sculptor/agents/pi_agent/agent_wrapper.py`; the source-directory
> authority is `get_skill_source_directories` in
> `sculptor/sculptor/web/skills.py`.

## The single source of truth for *where* skills come from

`get_skill_source_directories` (`web/skills.py:181-223`) is the one authority for
the skill roots, used by **both** `discover_skills` (which feeds the slash
picker) **and** `_build_skill_launch_args` (which feeds pi). They derive from the
same roots so the picker list and pi's loaded set stay in lockstep
(`agent_wrapper.py:891-909`, `_discover_skill_names` at `agent_wrapper.py:880-889`).

The sources, **in discovery order** (`web/skills.py:202-222`):

| # | Path | Kind | Namespaced? |
| --- | --- | --- | --- |
| 0 | `<plugin>/skills/` | `SKILL_DIR` | yes — plugin name from `.claude-plugin/plugin.json` |
| 1 | `<repo>/.claude/skills/` | `SKILL_DIR` | no |
| 2 | `<repo>/.claude/commands/` | `COMMAND_FILES` | no |
| 3 | `<home>/.claude/skills/` | `SKILL_DIR` | no |
| 4 | `<home>/.claude/commands/` | `COMMAND_FILES` | no |

`home` is overridable via `home_path` so it resolves against the agent's
environment, not the host (`web/skills.py:196-200`).

## Rule 1 — `SKILL.md` directories map cleanly

A `SKILL_DIR` source (a directory of `<name>/SKILL.md` subdirectories — the
agentskills.io standard) maps **directly** onto pi's own skill discovery: each
becomes a `--skill <path>` flag (`agent_wrapper.py:912-916`). Missing source dirs
are skipped quietly — a repo without `.claude/skills` is normal
(`agent_wrapper.py:913-914`).

## Rule 2 — plugin skills are passed **un-namespaced**

pi has no plugin-namespace concept; it registers plugin skills with their bare
names. So when Sculptor rewrites a picked skill invocation into pi's
`/skill:<name>` shape, a plugin-namespaced `<plugin>:<skill>` is **reduced to its
bare `<skill>`** (`_rewrite_skill_invocation` at `agent_wrapper.py:427-451`,
specifically `bare_name = name.rsplit(":", 1)[-1]` at line 450, "because pi
registers plugin skills un-namespaced" at lines 438-440).

- The frontend stays harness-agnostic: it sends `/name [args]` the same way it
  sends Claude. For pi, that becomes `/skill:<bare-name> [args]` when `name` is
  one of the discovered skills; otherwise the text passes through untouched.
- Test: `/sculptor-workflow:review` rewrites to `/skill:review`
  (`agent_wrapper_test.py`, `test_rewrite_skill_invocation_strips_plugin_namespace`).
- Pseudo-skills (`/clear`, `/copy`, `/btw`) are parsed frontend-side, never reach
  the rewrite, and pass through.

## Rule 3 — loose `.claude/commands/*.md` don't map directly (they're wrapped)

pi discovers skills **only** as `SKILL.md` directories, not the loose `.md`
command files Claude also supports. So a `COMMAND_FILES` source is **not** handed
to pi as-is. Instead each `*.md` is wrapped in a synthesized `SKILL.md`
directory, and the wrapper parent is passed as a single `--skill`
(`_build_skill_launch_args` at `agent_wrapper.py:917-921`;
`_synthesize_command_skills` at `agent_wrapper.py:924-958`).

The synthesized wrappers are written under the **per-task state dir**
(`<state>/pi_skills/<name>/SKILL.md`) — outside the repo and outside `~/.claude`
— so neither `discover_skills` nor pi's own ancestor auto-discovery lists them a
second time; only the explicit `--skill` loads them
(`agent_wrapper.py:929-938`). The file stem is the skill name and first-name-wins,
matching `discover_skills`' cross-source precedence.

## Rule 4 — a skill with no description does not load

pi **refuses to load a skill whose description is missing**
(`_render_synthesized_skill` at `agent_wrapper.py:454-464`, specifically lines
460-461). Sculptor defends against this for wrapped commands by synthesizing a
fallback description when the command file has none: `parse_command_frontmatter(body)
or f"Project command '{name}' (from {command_file.name})."`
(`agent_wrapper.py:954`). The rendered frontmatter always includes a `description`
(JSON-encoded and flattened to one line so colons/quotes can't break the YAML)
(`agent_wrapper.py:463-464`).

- Test: a command with no frontmatter still loads — a description is synthesized
  (`agent_wrapper_test.py`, around the synthesized-skill cases).

> Implication for hand-authored skills: a `SKILL.md` in a real `SKILL_DIR`
> source is passed to pi **directly** (Rule 1) — it is **not** run through the
> fallback-description synthesis, which only covers wrapped loose commands. So a
> hand-authored skill that omits `description` will silently fail to load in pi.
> Always give a skill a `description`.
