# Task 8.1: Skills — the workspace's skill set works under pi (`supports_skills`)

## Goal

The skill set a workspace shows under Claude is discoverable and
executable from a pi workspace — the slash picker lists it, invoking a
skill causes pi to follow it — and `supports_skills` flips `True`.
Feasibility verdict **(i) Sculptor-side only** (`feasibility.md` §7): pi
natively reads agentskills.io-standard `SKILL.md` directories (the same
shape Claude uses), accepts repeatable `--skill <path>` flags, documents
`~/.claude/skills` interop explicitly, enumerates skills via
`get_commands`, and invokes via `/skill:<name>` in a prompt.

## Requirements addressed

REQ-CAP-SKILLS; REQ-CAP-ALL-1..7; REQ-TEST-1/2/4.

## Background

Sculptor's skill list authority is `discover_skills(repo_path, plugin_dirs)`
(`sculptor/sculptor/web/skills.py:153-201`), scanning in priority order:
plugin `skills/` dirs → repo `.claude/skills/` (SKILL.md dirs) → repo
`.claude/commands/` (loose `.md`) → `~/.claude/skills/` →
`~/.claude/commands/` (first-name-wins). The frontend fetches it via
`GET /api/v1/skills` (`app.py:1489-1554`) for the slash picker and
SkillsPanel. Real (non-pseudo) skills reach Claude as message text;
Claude's own skill layer expands them.

The base tranche (PR #54) landed the gates this task flips live:
`SkillsPanel` and the slash-picker skill rows are **suppressed** for a
non-supporting harness (suppression was the sanctioned fallback for
picker/panel surfaces — no tooltip), pinned by
`test_skills_panel_empty_under_pi`
(`test_pi_capability_gating.py:146`); reads go through
`useTaskSupportsSkills` (`useTaskHelpers.ts:49`).

Parity bar (REQ-CAP-SKILLS): the FULL Claude-visible set — all sources.
Feasibility's recorded caveat: SKILL.md-directory skills map cleanly;
**loose command-style `.md` files** (`.claude/commands/*.md`) and
*plugin* skills need verification at tranche time — pi's loose-`.md`
discovery depends on location class (`<pi-pkg>/docs/skills.md:36-41`).
If a source class doesn't map, the residual is a recorded divergence
note under the strict rule's per-tranche judgment (REQ-CAP-ALL-1 — with
the override valve and `CAPABILITY-GAP` marker if you and Danver judge a
flip warranted despite it; pause and ask rather than deciding alone).

Wire facts (`feasibility.md` §7): skill sources — `~/.pi/agent/skills/`,
`~/.agents/skills/`, project `.pi/skills/` + `.agents/skills/`, package
`skills/`, settings `skills` array, and `--skill <path>` (repeatable,
additive even with `--no-skills`); `get_commands` returns
`{"name":"skill:<name>","source":"skill","sourceInfo":{path,scope,...}}`;
invocation = `/skill:<name> [args]` in a `prompt` (input expansion
expands it); models also auto-load skills by description.

## Files to modify/create

- `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` — `start()`:
  pass the workspace's skill sources to pi as repeatable `--skill <path>`
  flags. Source the list from the same roots `discover_skills` scans
  (repo `.claude/skills`, `~/.claude/skills`, plugin skill dirs — share
  the path-derivation rather than duplicating constants; consider a
  small helper in `web/skills.py` exposing the source DIRECTORIES so the
  two stay in lockstep). Decide and document the loose-`.claude/commands`
  handling per your verification (see Implementation 2).
- Prompt assembly: map an invoked Sculptor skill into pi's invocation
  shape. Decide the seam deliberately: either the frontend sends the
  same `/name args` text it sends Claude and `PiAgent` rewrites a
  leading `/name` to `/skill:<name>` when `name` is in the discovered
  set, or the picker emits the pi shape for pi workspaces. Prefer the
  backend rewrite (keeps the frontend harness-agnostic); implement in
  the prompt-assembly path of `_process_message_queue`.
- `sculptor/sculptor/agents/pi_agent/harness.py` — flip
  `supports_skills=True`; update stance comment.
- `sculptor/sculptor/agents/pi_agent/harness_test.py`,
  `agent_wrapper_test.py` — stances + the rewrite/flag-assembly units.
- Frontend — no new code expected: the suppression branches read the
  flag and flip live (SkillsPanel renders, picker rows appear). Verify
  rather than re-wire.
- `sculptor/tests/integration/frontend/test_pi_capability_gating.py` —
  flip `test_skills_panel_empty_under_pi`: the panel now lists skills
  under pi; picker rows present.
- `sculptor/sculptor/testing/fake_pi.py` — accept `--skill` flags
  (parse_known_args already tolerates extras — make them first-class so
  tests can assert they were passed); optionally echo a scripted
  "skill followed" behavior for `/skill:<name>` prompts.
- **Create** `sculptor/tests/integration/real_pi/test_skills.py` — a
  workspace-local `.claude/skills/<test-skill>/SKILL.md` with a sentinel
  instruction ("when invoked, reply exactly SKILL-OK-<n>"); invoke via
  the picker path; assert the sentinel behavior.

## Implementation details

1. Launch-flag assembly: absolute paths; skip non-existent dirs quietly
   (a repo without `.claude/skills` is normal). Keep the flag order
   deterministic so `get_commands`-based debugging is stable.
2. Verify the two flagged source classes empirically EARLY (this is the
   tranche's REQ-INV-6 hotspot): (a) loose `.claude/commands/*.md` —
   does `--skill` accept a loose-file dir / do they surface? (b) plugin
   skills — same question for plugin `skills/` dirs. Map what maps;
   record what doesn't as the divergence note; pause and ask Danver if
   the gap looks flip-blocking under the strict rule.
3. First-name-wins parity: `discover_skills` dedupes by name across
   sources; pi has its own precedence. A skill shadowed differently in
   the two systems is a subtle divergence — compare `get_commands`
   output against `discover_skills` for a fixture workspace in an
   integration test and document any ordering differences.
4. The `/skill:` rewrite must not fire for pseudo-skills (`/clear`,
   `/copy`, `/btw` — `pseudoSkills.ts` parses those frontend-side and
   they never reach the prompt) nor for plain text starting with `/`
   that is not a discovered skill name.

## Testing suggestions

- Unit: flag assembly from fixture dirs; the `/name` → `/skill:<name>`
  rewrite (hits, misses, pseudo-skill exclusions).
- Integration (fake_pi): picker lists skills under pi; invoking one sends
  the rewritten prompt (assert via fake_pi); flipped panel test.
- Real (`real_pi/test_skills.py`): sentinel skill followed end-to-end;
  optionally assert `get_commands` lists it. Full `just test-real-pi`
  green at merge.

## Gotchas

- pi auto-loads skills by description (progressive disclosure) — a test
  skill with an over-broad description may fire un-invoked; keep test
  skill descriptions narrow and prompts explicit.
- `--no-skills` is NOT passed (it would disable pi's own discovery;
  `--skill` is additive anyway) — but be aware pi ALSO discovers its own
  source classes (`~/.pi/agent/skills`, `.agents/skills`, ...). Those
  extra-Claude sources appearing under pi is acceptable surplus, not a
  parity violation — note it in the MR.
- Coordinate the `command = [...]` launch-args line with phases 06/07
  (session-dir, extensions) — rebase carefully.
- The skills endpoint and `discover_skills` are shared with Claude —
  changes there must be additive (a directories-exposing helper, not a
  behavior change). Claude regression here is the one real hazard:
  deterministic gates + the FakeClaude skill tests cover it.
- Tranche conventions: own workspace on `danver/pi-capabilities-skills`
  rooted at current `origin/main` (≥ `99cbc0d`), MR → `main`;
  `just rebuild` first; commit rules (`just format`/`check`/`test-unit`,
  trailer `Co-authored-by: Sculptor <sculptor@imbue.com>`); integration
  tests via the repo's integration-test skill; evidence bundle in the MR
  (deterministic gates, FULL `just test-real-pi`, real-claude rerun — ask
  Danver if prerequisites are missing; ticked checklist); PR
  world-readable ending `(Sent by Claude)`; announce per
  post-mr-to-slack; pause for Danver before any deferral (REQ-INV-6).

## Verification checklist

- [ ] A pi workspace's picker/panel lists the workspace's Claude-visible
      skills; invoking one causes pi to follow the SKILL.md.
- [ ] Source-class verification recorded: SKILL.md dirs (must map),
      loose `.claude/commands` and plugin skills (mapped, or divergence
      note + Danver-consulted judgment).
- [ ] Rewrite seam unit-covered incl. pseudo-skill exclusions.
- [ ] `supports_skills=True`; stance tests updated; skills
      CAPABILITY-GAP markers (`TipTapConfig.ts:341` region) resolved;
      flipped `test_skills_panel_empty_under_pi`.
- [ ] Integration tests: flipped gating test, `test_pi_basic.py`,
      `test_minimum_interface_conformance.py`; new
      `real_pi/test_skills.py`; full `real_pi/` green at merge.
