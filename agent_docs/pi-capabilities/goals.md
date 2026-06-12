# pi-capabilities — Goals

Phase 5 of the pi multi-harness initiative (cycle slug: `pi-capabilities`).

## Problem / Motivation

- pi shipped (phases 3–4) as a **degraded** harness: it runs and is fully
  provisioned, but advertises 11 of its 12 capability flags as `False` (only
  `supports_file_references` is `True`).
- Each `False` flag switches off a real Sculptor affordance for pi
  workspaces: rich tool-call rendering, the Stop button, context compaction,
  session resume, skills, sub-agents, image input, file attachments,
  background tasks, and the interactive backchannel (plan mode /
  ask-user-question).
- pi is therefore usable-but-thin and cannot be considered **graduated**
  (daily-usable) until these capabilities fill in.
- pi's runtime is **not ours to modify**: Sculptor can extend pi only by
  folding simple plugins into its pinned, immutable plugin set. Which
  capabilities that can actually unlock is not yet known.

## Goal

Turn pi's capability flags `True` as genuine support lands, moving pi from
degraded toward graduated — with Claude's experience unchanged throughout.

- **Incremental, parallel tranches.** The work splits into small, independent
  tranches that progress in parallel, each landing on its own as a separate
  commit in its own workspace. A slow or blocked tranche delays only itself.
- **pi-plugin-only reach.** pi-core is immutable and outside our control.
  pi-side work is limited to adding simple plugins (and equivalent extension
  points) to Sculptor's pinned pi plugin set, plus Sculptor-side wiring. A
  capability not achievable that way is **deferred** — not forced.
- **Up-front feasibility investigation.** Before committing tranches,
  investigate which targets are reachable via plugins versus blocked on
  pi-core. This triage decides what is pursued now and what defers.
- **Acquisition levers.** Capabilities come mostly from added plugins. A
  pinned-version bump is not expected to unlock capability, but is taken
  opportunistically if it does.
- **Targets.** Every currently-`False` flag is in scope except
  `supports_fast_mode`, which has no natural mapping to pi's models for now.
  *(Amended during the requirements session, 2026-06-11:
  `supports_compaction` conflated two mechanisms — `/clear` is a context
  reset, auto-compaction is in-place summarization — with distinct
  semantics and feasibility. It splits into `supports_context_reset` and
  `supports_compaction`; both halves are targets, making 11 target flags.
  See requirements.md.)*
- **Shared groundwork first.** Capability-gate reads currently fail *open* on
  a mistyped field (FOLLOWUPS-9); hardening them lands first as a shared base
  so every later tranche gates safely. After that, parallelize as far as
  possible and sequence only where a real dependency requires it.

## Success criteria

- **Per tranche:** the capability flag is `True` for pi, its gate is correctly
  wired (no fail-open, no dead affordance), and it carries tests — including
  `real_pi/` conformance coverage for that capability.
- **Conformance grows with parity:** each tranche extends pi's `real_pi/`
  suite (a sibling to the existing `real_claude/` suite) as pi reaches parity.
- **No regression on Claude:** every tranche keeps the deterministic gates
  green on a single run and the stochastic real-Claude gate green on a rerun.
- **Graduation (overall):** a subjective maintainer judgment that pi is
  daily-usable, weighing capability completeness against effort. It is not a
  fixed automated gate.

## Audience

- Primarily the **orchestration workflow / spec pipeline** that consumes this
  document to drive the downstream requirements, architecture, and
  implementation-plan sessions and the per-tranche implementation cycles.
- Secondarily, the maintainers and cycle agents who scope and build each
  tranche.
