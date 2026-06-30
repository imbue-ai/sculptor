---
name: pi
description: |
  Point at the living pi-integration reference (agent_docs/pi-integration/).
  Use at the start of any task that touches Sculptor's pi harness integration —
  RPC model selection, CLI launch flags, provider auth, or skills mapping — so
  you read the consolidated facts instead of re-deriving them from the code.
---

# pi Integration Reference

`pi` is a third-party, version-pinned, **immutable** coding-agent harness that
Sculptor drives as a subprocess. Sculptor never modifies pi-core; it extends pi
only through a pinned extension set plus Sculptor-side wiring.

Before changing or reasoning about any pi-integration surface, read the living
reference under [`agent_docs/pi-integration/`](../../../agent_docs/pi-integration/README.md):

- **[README.md](../../../agent_docs/pi-integration/README.md)** — invariants:
  pi-core immutability, the pinned-version + pinned-extension model, the current
  pin, and where the de-facto live reference lives (the `harness.py` /
  `agent_wrapper.py` module docstrings).
- **[rpc.md](../../../agent_docs/pi-integration/rpc.md)** — the model-selection
  RPC trio (`get_available_models` / `get_state` / `set_model`); why model
  identity is `(provider, modelId)` fetched at runtime, not Sculptor's
  `LLMModel` enum.
- **[cli-flags.md](../../../agent_docs/pi-integration/cli-flags.md)** — the full
  launch argv and `--session-id` resume semantics.
- **[auth.md](../../../agent_docs/pi-integration/auth.md)** —
  `~/.pi/agent/auth.json` as the shared source of truth; presence-not-validity
  catalog gating; per-provider `/logout`.
- **[skills.md](../../../agent_docs/pi-integration/skills.md)** — how Sculptor's
  skills/commands map onto pi's `--skill`.

The reference cites a live source file for every non-obvious claim. Citations
drift — re-confirm against the cited file before acting, and update the doc in
the same change if the code has moved.
