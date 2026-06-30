# pi CLI — Launch Flags

The exact command line Sculptor builds to launch pi, and the behavior of the
load-bearing flags.

> Source of truth: `PiAgent.start()` in
> `sculptor/sculptor/agents/pi_agent/agent_wrapper.py`. The argv is assembled at
> `agent_wrapper.py:708-721`.

## The full argv

```
pi \
  --mode rpc \
  --session-dir <state>/<PI_SESSION_DIR_NAME> \
  --session-id <sculptor-pinned id> \
  --no-extensions \
  -e <state>/sculptor_backchannel.ts \
  -e <state>/sculptor_subagent.ts \
  -e <state>/sculptor_background.ts \
  --append-system-prompt <assembled prompt> \
  [--skill <dir> ...]
```

| Flag | Purpose | Built at |
| --- | --- | --- |
| `--mode rpc` | JSONL request/response protocol over stdin/stdout | `agent_wrapper.py:710-711` |
| `--session-dir <dir>` | Per-task directory holding the persisted JSONL session | `agent_wrapper.py:712-713`; dir is `get_state_path() / PI_SESSION_DIR_NAME` (`agent_wrapper.py:681`) |
| `--session-id <id>` | The Sculptor-pinned session id — the resume lever | `agent_wrapper.py:714-715` |
| `--no-extensions` | Disables pi's **own** extension discovery | `agent_wrapper.py:716` |
| `-e <path>` (×3) | Loads each pinned extension explicitly | `agent_wrapper.py:717`; `_install_pinned_extensions` at `agent_wrapper.py:960-984` |
| `--append-system-prompt <prompt>` | Sculptor's assembled system prompt | `agent_wrapper.py:718-719`; `_build_system_prompt` |
| `--skill <dir>` (×N) | Workspace's Claude-visible skill sources | `agent_wrapper.py:720`; `_build_skill_launch_args` at `agent_wrapper.py:891-922` (see [skills.md](./skills.md)) |

The process is then started with `isolate_process_group=True` so a Stop/shutdown
signal cascades to pi's descendants (e.g. a background-tool child)
(`agent_wrapper.py:722-733`).

## `--no-extensions` plus `-e` is the immutability lever

These two are a pair. `--no-extensions` turns off pi's own extension discovery;
the explicit `-e <path>` flags then load **only** Sculptor's curated, pinned set.
Together they enforce the invariant that nothing but Sculptor's three
version-pinned extensions ever loads (`agent_wrapper.py:704-707`). See the
[pinned-extension model](./README.md#the-pinned-extension-model) in the README.

## `--session-id` (not `--session`) and its behavior

Sculptor pins the session id **Sculptor-side** and passes it with `--session-id`.
This was a deliberate choice over `--session <id>`
(`agent_wrapper.py:699-704`):

- **Adopts the id verbatim.** pi takes the `--session-id` value exactly as given;
  a reported id that differed would signal a pi-behavior change, which
  `_verify_resumed_session` logs loud (`agent_wrapper.py:1083-1091`,
  `1100-1107`).
- **Creates the session if missing.** `--session-id` never errors on an
  absent/corrupt session — pi creates one with that id. (Real pi `0.78.0` was
  observed to exit non-zero for an unknown `--session`, which would crash-loop.)
  A lost session file therefore degrades to a **loud fresh start**, not a crash
  (`agent_wrapper.py:699-704`, `1108-1112`).
- **Tolerant of a truncated JSONL tail.** If the persisted session file has a
  corrupt/truncated tail, pi resumes the **valid prefix** rather than failing
  (`agent_wrapper.py:703`).

### How resume actually works

- On first launch, Sculptor mints an id (`generate_id()`), writes it to
  `PI_SESSION_ID_STATE_FILE`, and passes it. On a later launch it reads that file
  back; a present file means "resume" (`agent_wrapper.py:680-689`).
- After a `new_session` (context clear), pi mints a **new** id; Sculptor reads it
  back via `get_state` and overwrites the state file so the next resume targets
  the post-clear session (`_persist_post_clear_session_id` at
  `agent_wrapper.py:1722-1743`).
- The per-task session dir lives under the environment state path, so parallel pi
  workspaces never share a session.

## Credentials are not passed as flags

Neither `--provider` nor `--api-key` appears anywhere in the launch — confirmed
absent from `agent_wrapper.py`. API keys flow through the **process environment**
as `Secret`s instead (`_collect_api_key_secrets` at `agent_wrapper.py:986-993`),
and model choice is made over RPC. See [rpc.md](./rpc.md) and [auth.md](./auth.md).
