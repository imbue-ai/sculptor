# pi RPC — Model Selection

How Sculptor reads pi's model catalog, reads pi's session state, and switches
pi's model — all over the JSONL RPC channel, never via CLI flags.

> Source of truth: the wire-protocol narrative in
> `sculptor/sculptor/agents/pi_agent/agent_wrapper.py` (module docstring) and the
> three blocking request helpers cited below. The RPC requests/responses below
> are taken from the live `_send_rpc` call sites and the
> `agent_wrapper_test.py` fixtures.

## The three methods

All three are request/response RPC commands: Sculptor sends `{"type": <command>,
"id": <request_id>, …}` on stdin and waits (between turns) for a matching
`{"type": "response", "command": <command>, "id": <request_id>, "success": …,
"data": …}` on stdout. The match is on `(command, id)`
(`_consume_until_command_response` at `agent_wrapper.py:1064`).

### `get_available_models` — fetch the catalog at runtime

`_request_available_models_blocking` (`agent_wrapper.py:1116-1134`).

```jsonc
// request
{"type": "get_available_models", "id": "<request_id>"}
// response.data
{"models": [{"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}, ...]}
```

Returns the raw `data.models` list (each a dict). Returns `[]` on timeout,
process exit, or a malformed payload (`agent_wrapper.py:1129-1134`).

### `get_state` — read the session's id, message count, and current model

`_request_state_blocking` (`agent_wrapper.py:1068-1081`).

```jsonc
// request
{"type": "get_state", "id": "<request_id>"}
// response.data (RpcSessionState)
{"sessionId": "...", "messageCount": 1, "model": {"id": "...", "name": "...", "provider": "..."}}
```

Used for two safety checks beyond model display:
- **Resume verification** — `_verify_resumed_session` (`agent_wrapper.py:1083-1114`)
  confirms pi resumed the `--session-id` we asked for and that the session is
  non-empty; both anomalies are logged loud so context loss is never silent.
- **Post-clear id capture** — `_persist_post_clear_session_id`
  (`agent_wrapper.py:1722-1743`) reads back the fresh session id after a
  `new_session` so a later resume targets it.

### `set_model` — switch the model

`_handle_set_model` (`agent_wrapper.py:1745-1789`); a non-raising variant
`_request_set_model_blocking` (`agent_wrapper.py:1136-1154`) backs the internal
auto-reselect.

```jsonc
// request
{"type": "set_model", "id": "<command_id>", "provider": "anthropic", "modelId": "claude-opus-4-8"}
// response.data — the new current Model
{"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
```

Note the request key is **`modelId`** (camelCase), distinct from the `model_id`
field Sculptor uses internally.

**Session-level and persistent — one mechanism, not two.** `set_model` applies to
the live session **and persists for later turns** within it
(`agent_wrapper.py:1749-1750`). There is no separate "default model" RPC: the
selection is written into pi's persisted session, so it survives a process
resume *because the session itself is resumed* (`--session-id`, see
[cli-flags.md](./cli-flags.md)). On success pi returns the new `Model`; Sculptor
re-emits a `ModelsAvailableAgentMessage` (same catalog, new current model) so the
persisted selection and the switcher follow. A `success:false` (e.g. `Model not
found`) or no acknowledgement raises `PiSetModelError` and leaves the current
model unchanged (`agent_wrapper.py:1765-1774`).

### Concurrency constraint

All three helpers share a **sole-reader** safety constraint: they consume pi's
stdout directly, so they are only safe to call **between turns**, when the
message-processing thread is not also reading the queue
(`agent_wrapper.py:1071-1072`, `1748-1749`). Model commands are routed through
the `_input_agent_messages` FIFO to guarantee this.

## Model identity is `(provider, modelId)`, not the `LLMModel` enum

A pi model is identified by a **`(provider, modelId)` pair**, not by Sculptor's
internal `LLMModel` enum. The whole catalog is therefore **fetched at runtime**
and cannot be hardcoded:

- `_model_option_from_pi` (`agent_wrapper.py:360-376`) maps one pi `Model` dict
  `{id, name, provider, …}` onto a `ModelOption(provider, model_id,
  display_name)`. `provider` defaults to `"anthropic"` when pi omits it (Sculptor
  launches pi against the Anthropic catalog); `display_name` falls back to the
  id.
- `ModelOption` lives in `sculptor/sculptor/state/messages.py` — a free-form
  `(provider, model_id, display_name)` triple, deliberately **not** an enum, so
  any provider/model pi reports can flow through.
- `_curate_models` (`agent_wrapper.py:321-357`) trims pi's raw catalog
  (blacklist, dated-pin duplicates, newest-first sort) but always keeps the
  current model so the switcher is never empty — it operates on whatever pi
  returned, not a fixed list.

Practical consequence: **never hardcode pi model ids in Sculptor.** Call
`get_available_models` and pick from what pi reports.

## Do not pass `--provider` or `--api-key`

Model selection is **entirely an RPC concern**. Neither `--provider` nor
`--api-key` is ever passed on pi's command line (`grep` finds neither anywhere in
`agent_wrapper.py`; the full argv is in [cli-flags.md](./cli-flags.md) and at
`agent_wrapper.py:708-721`).

Credentials reach pi a different way: API keys are read from the **process
environment** at launch and injected as `Secret`s
(`_collect_api_key_secrets` at `agent_wrapper.py:986-993`, passed as
`secrets=` to `run_process_in_background` at `agent_wrapper.py:724`). Which
provider is authenticated is governed by `~/.pi/agent/auth.json` plus env vars —
see [auth.md](./auth.md). The model *choice* is then made over RPC against
whatever catalog those credentials unlock.
