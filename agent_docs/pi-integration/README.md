# pi Integration — Living Reference

A consolidated, **living** reference for how Sculptor integrates the third-party
`pi` harness. The goal is narrow: stop every pi integration cycle from
re-deriving the same RPC / CLI / auth / skills facts from scratch. Each page
below summarizes one surface and **cites a live source file for every
non-obvious claim**, so when the code moves, the doc has a fixed point to be
checked against.

> **Verify before you trust.** Citations are `path:line` against the tree at
> commit `5a0d94bb` (2026-06-30). Line numbers drift; treat them as a pointer to
> the right function, and re-confirm against the file before acting. If a cited
> claim no longer matches the code, **the code is the source of truth** — fix
> this doc.

## What pi is (and the one invariant that governs everything)

`pi` is a separate, upstream coding-agent harness (the
[`earendil-works/pi`](https://github.com/earendil-works/pi) project) that
Sculptor drives as a subprocess over a JSONL RPC protocol. It is **not ours to
modify**.

**pi-core is immutable.** Sculptor never patches, forks, or rebuilds pi. Every
pi-side capability Sculptor adds is reached through exactly two seams:

1. **The pinned extension set** — a small, version-pinned set of TypeScript
   extensions that Sculptor ships and loads explicitly (see
   [the pinned-extension model](#the-pinned-extension-model) below).
2. **Sculptor-side wiring** — the adapter code in
   `sculptor/sculptor/agents/pi_agent/` that maps pi's wire protocol onto
   Sculptor's harness-agnostic contracts, plus driving pi's own interactive
   commands (e.g. `/login`, `/logout`) through a PTY.

Anything that would require changing pi-core itself is **out of scope** — it
defers until the pinned version is bumped to a pi release that already supports
it. When you read "X is not supported," read it as "the pinned pi version does
not expose X," not "we could patch it in."

## The pinned-version model

Sculptor pins pi to **one exact version** so the RPC schema, CLI flags, and
session format stay known and testable.

| Fact | Value | Source of truth |
| --- | --- | --- |
| Current pinned version | **`0.80.2`** | `sculptor/sculptor/services/pi_version.py:10` (`PI_PINNED_VERSION`) |
| Per-platform download pin (asset + sha256) | darwin-arm64 / darwin-x64 / linux-x64 | `sculptor/sculptor/services/managed_tools.py:66-82` (`PI_PIN`) |
| Allowed version range | min == max == recommended == the pin | `sculptor/sculptor/services/managed_tools.py:170-174` (`PI_VERSION_RANGE`) |
| Release source | `https://github.com/earendil-works/pi/releases/download` | `sculptor/sculptor/services/managed_tools.py:165` (`_PI_RELEASE_BASE_URL`) |
| Bump path | `just compute-pi-pin <version>` → paste the printed `platforms={...}` block into `PI_PIN`, then update `PI_PINNED_VERSION` | `scripts/compute_pi_pin.py`; `justfile:937-938` |

pi publishes no checksums of its own, so Sculptor computes them per version and
bakes them into `PI_PIN`; the install path verifies every download against the
baked sha256 (`managed_tools.py:51-63`, `PiManagedTool.resolve_distribution` at
`managed_tools.py:197-208`). The version string lives in its own dependency-free
module (`pi_version.py`) so the test harness's `fake_pi` stub can answer
`pi --version` without importing the heavier `managed_tools` stack.

> **Watch for stale version strings.** Doc-style version references inside the
> code can lag the real pin. As of this writing the `agent_wrapper.py` module
> docstring still cites "pi 0.78.0" (`agent_wrapper.py:35`) and the
> `compute_pi_pin.py` usage examples use `0.78.0` — both are illustrative text,
> not the live pin. The live pin is **`0.80.2`** (`pi_version.py:10`). Trust the
> constant, not the prose.

## The pinned-extension model

pi has its own extension-discovery mechanism. Sculptor **disables it** and loads
only its own curated set, so the immutability guarantee holds (only Sculptor's
version-pinned extensions ever run):

- Launch passes `--no-extensions` (disables pi's own discovery) **and** an
  explicit `-e <path>` for each pinned extension
  (`agent_wrapper.py:704-707`, `_install_pinned_extensions` at
  `agent_wrapper.py:960-984`).
- The pinned set is three TypeScript extensions shipped as package data next to
  the agent module (`sculptor/sculptor/agents/pi_agent/extensions/`):
  - `sculptor_backchannel.ts` — ask-user-question + plan mode
  - `sculptor_subagent.ts` — sub-agents (each child is its own `pi` process)
  - `sculptor_background.ts` — background tasks
- `PI_PIN.plugin_set_revision` is a reserved constant (`"bundled"`) — a sentinel
  slot for pinning a pi *plugin* set if one is ever needed
  (`managed_tools.py:61-63`).

## The de-facto live reference already lives in two module docstrings

This doc **summarizes and links**; it deliberately does not re-derive the
protocol. The authoritative, code-adjacent narratives are:

- **`sculptor/sculptor/agents/pi_agent/harness.py`** (module docstring,
  lines 1-35) — the capability declaration: what pi supports and why. The
  truthful, gated values are the `capabilities()` override at
  `harness.py:85-158`, which consumers read.
- **`sculptor/sculptor/agents/pi_agent/agent_wrapper.py`** (module docstring,
  lines 1-36) — the wire-protocol narrative: how the subprocess is launched,
  how the three stdout channels multiplex, how tool calls render, how
  sub-agents/background tasks yield.

Read those first. The pages here are the index and the fast-path summary.

### Capability snapshot (from `capabilities()`, `harness.py:85-158`)

| Capability | Pinned pi (`0.80.2`) | Mechanism |
| --- | --- | --- |
| Tool-use rendering | ✅ `True` | tool-execution lane → harness tool blocks |
| Session resume | ✅ `True` | `--session-dir` / `--session-id` persisted JSONL |
| Skills | ✅ `True` | `--skill <dir>` flags (see [skills.md](./skills.md)) |
| Interactive backchannel (ask-user / plan mode) | ✅ `True` | `sculptor_backchannel` extension |
| Sub-agents | ✅ `True` | `sculptor_subagent` extension |
| Background tasks | ✅ `True` | `sculptor_background` extension |
| Model selection | ✅ `True` | RPC `set_model` (see [rpc.md](./rpc.md)) |
| Fast mode | ❌ `False` | no natural mapping to pi's models |

The truthful, gated declaration is the `capabilities()` override in `harness.py`
— prefer it over this table if they ever disagree.

## Pages

| Page | Covers |
| --- | --- |
| [rpc.md](./rpc.md) | The model-selection RPC trio — `get_available_models`, `get_state`, `set_model`; why model identity is `(provider, modelId)` fetched at runtime, not Sculptor's `LLMModel` enum; why no `--provider` / `--api-key` flags |
| [cli-flags.md](./cli-flags.md) | The full launch argv; `--session-id` (not `--session`) and its adopt-verbatim / create-if-missing / corrupt-tail-tolerant behavior; `--session-dir`, `--no-extensions`, `-e`, `--append-system-prompt`, `--skill` |
| [auth.md](./auth.md) | `~/.pi/agent/auth.json` as the shared source of truth; presence-not-validity catalog gating; auth.json-vs-env precedence; per-provider `/logout`; `getAgentDir` (`PI_CODING_AGENT_DIR`) resolution |
| [skills.md](./skills.md) | How Sculptor's skills/commands map onto pi's `--skill`; un-namespaced plugin skills; loose `.claude/commands` wrapping; the no-description-doesn't-load rule; the full skill-source list |

## Related cycles

- **`agent_docs/pi-auth/`** (on `main`) — the spec/architecture/requirements/
  review/mocks for organic provider auth from Settings. [auth.md](./auth.md)
  builds directly on it; that folder is the deeper dive on the auth UX and the
  empirical phase-0 feasibility findings.
- **`agent_docs/pi-capabilities/`** — **not on `main`.** It lives only on an
  unmerged `pi-capabilities` working branch (search the repo's branches for the
  `pi-capabilities` slug). Its capability-matrix content could be folded into
  this reference once it lands; until then, do not assume it is present. (Do not
  merge that branch as part of a docs task.)

## How to keep this living

When you touch any pi-integration surface, update the matching page here in the
same change, and re-check that the cited `path:line` still points at the claim.
A page that cites code is only useful while the citation is true.

---

_This is an internal engineering reference, not user-facing documentation._
