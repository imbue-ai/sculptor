"""pi catalog discovery: a short-lived ``pi --mode rpc`` probe that fetches + curates the model list.

Two callers share this module so their catalogs cannot disagree:

- the in-workspace pre-message probe (``PiAgent.fetch_available_models_probe``),
  which spawns pi through the agent's execution environment, and
- the host-side pre-workspace probe (``probe_catalog_on_host``), which spawns pi
  directly on the backend host to feed pre-create surfaces such as the New
  Workspace modal's pi model picker.

The probe launches a minimal pi (no extensions / skills / system prompt)
against a throwaway session, issues only the ``get_available_models`` and
``get_state`` RPCs, then shuts the process down. Curation and the
authenticated-provider filter live here too, shared by the probes and the
agent wrapper's start-time fetch.
"""

import json
import os
import re
import time
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from queue import Empty
from typing import Any

from loguru import logger
from packaging.version import InvalidVersion
from packaging.version import Version

from sculptor.agents.pi_agent.authenticated_providers import compute_authenticated_provider_ids
from sculptor.agents.pi_agent.output_processor import RpcResponse
from sculptor.agents.pi_agent.output_processor import parse_rpc_message
from sculptor.foundation.common import generate_id
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.processes.local_process import run_background
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import parse_pi_version
from sculptor.state.messages import ModelOption
from sculptor.utils.build import get_sculptor_folder

# The throwaway session dir the catalog probe launches pi against. Distinct from
# PI_SESSION_DIR_NAME so the probe's short-lived session never collides with the
# real conversation session the agent later resumes.
PI_PROBE_SESSION_DIR_NAME: str = "pi_probe_session"

# How long each blocking read of pi's stdout queue waits before the drain loop
# re-checks shutdown / process-exit; small so an exit is noticed promptly.
STDOUT_QUEUE_POLL_SECONDS: float = 0.1

# How long a model fetch waits for pi's get_available_models / get_state
# responses before giving up.
MODEL_FETCH_TIMEOUT_SECONDS: float = 10.0

# Obsolete model ids pi's get_available_models returns that the switcher must not
# offer — the whole pre-4 `claude-3-*` family (the live Anthropic catalog still
# lists these). Curation drops any id in this set (curate_models).
_PI_MODEL_BLACKLIST: frozenset[str] = frozenset(
    {
        "claude-3-5-haiku-20241022",
        "claude-3-5-haiku-latest",
        "claude-3-5-sonnet-20240620",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-sonnet-latest",
        "claude-3-7-sonnet-20250219",
        "claude-3-7-sonnet-latest",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-opus-latest",
        "claude-3-sonnet-20240229",
    }
)

# A "dated pin" model id ends in an 8-digit date (e.g. claude-opus-4-1-20250805).
# pi lists these alongside the friendly alias for the same model (claude-opus-4-1),
# so curation drops the dated duplicate and keeps the alias.
_DATED_PIN_SUFFIX_RE = re.compile(r"-\d{8}$")

# Captures the trailing major.minor version of a pi model id (e.g. the (4, 8) in
# claude-opus-4-8, the (4, 0) in claude-opus-4-0) for the newest-first sort.
_MODEL_VERSION_RE = re.compile(r"-(\d+)-(\d+)$")


def _model_sort_key(model: ModelOption) -> tuple[int, int, str]:
    """Newest-first sort key: descending (major, minor), then id for stability.

    Parses the trailing `-<major>-<minor>` of the model id (e.g. claude-opus-4-8
    → (4, 8)); ids without that shape sort last. The id tiebreaker keeps the order
    deterministic across same-version families.
    """
    match = _MODEL_VERSION_RE.search(model.model_id)
    if match is None:
        return (1, 0, model.model_id)
    major, minor = int(match.group(1)), int(match.group(2))
    return (-major, -minor, model.model_id)


def curate_models(
    models: list[ModelOption],
    current_model: ModelOption | None,
    authenticated_providers: set[str] | None = None,
) -> list[ModelOption]:
    """Trim pi's raw catalog to the models the switcher should offer, newest-first.

    Drops the obsolete `_PI_MODEL_BLACKLIST` ids and dated-pin duplicates
    (`_DATED_PIN_SUFFIX_RE`), then sorts newest-first (`_model_sort_key`). The
    current model is always kept even if a rule would drop it, so the switcher
    never shows an empty selection. Duplicate ids are de-duplicated, first-wins.

    When `authenticated_providers` is provided, options whose `provider` is not in
    that set are also dropped — pi gates its catalog on credential presence, not
    validity, so a stray ambient key would otherwise leak that provider's models
    into the picker. `None` (the default) disables the filter. The current model is
    exempt from every rule, including this one.
    """
    kept: list[ModelOption] = []
    seen_ids: set[str] = set()
    current_id = current_model.model_id if current_model is not None else None
    for model in models:
        if model.model_id in seen_ids:
            continue
        is_current = model.model_id == current_id
        if not is_current and model.model_id in _PI_MODEL_BLACKLIST:
            continue
        if not is_current and _DATED_PIN_SUFFIX_RE.search(model.model_id):
            continue
        if not is_current and authenticated_providers is not None and model.provider not in authenticated_providers:
            continue
        seen_ids.add(model.model_id)
        kept.append(model)
    # The current model must be offered even if pi did not list it in the catalog.
    if current_model is not None and current_id not in seen_ids:
        kept.append(current_model)
    return sorted(kept, key=_model_sort_key)


def model_option_from_pi(raw: Mapping[str, Any]) -> ModelOption | None:
    """Map one pi Model dict (`{id, name, provider, …}`) to a `ModelOption`.

    Returns None when the required `id` is missing/empty. `provider` defaults to
    "anthropic" (Sculptor launches pi against the Anthropic catalog) and the
    display name falls back to the id when pi omits `name`.
    """
    model_id = raw.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None
    provider = raw.get("provider")
    name = raw.get("name")
    return ModelOption(
        provider=provider if isinstance(provider, str) and provider else "anthropic",
        model_id=model_id,
        display_name=name if isinstance(name, str) and name else model_id,
    )


def pi_version_in_range(version: str) -> bool:
    try:
        v = Version(version)
    except InvalidVersion:
        return False
    return Version(PI_VERSION_RANGE.min_version) <= v <= Version(PI_VERSION_RANGE.max_version)


def send_rpc_line(process: RunningProcess, payload: Mapping[str, Any]) -> None:
    """Write one JSON-RPC line to pi's stdin, best-effort."""
    line = json.dumps(payload, separators=(",", ":")) + "\n"
    try:
        process.write_stdin(line)
    except Exception as e:  # noqa: BLE001
        logger.debug("pi rpc write_stdin failed: {}", e)


def consume_until_command_response(
    process: RunningProcess, command: str, command_id: str, timeout: float
) -> RpcResponse | None:
    """Drain pi's stdout until the `response` for (command, command_id) arrives.

    Correlates by id (RPC §5.1), skipping any session events pi emits meanwhile;
    returns None on timeout / process exit. It reads the process queue, so it is
    ONLY safe when the caller is the SOLE reader of that queue: a probe process,
    or an agent's process before its message-processing thread starts / between
    turns. Never call it while a turn is streaming — the turn pump would race it
    for the same queue.
    """
    out_queue = process.get_queue()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.is_finished() and out_queue.empty():
            return None
        try:
            line, is_stdout = out_queue.get(timeout=STDOUT_QUEUE_POLL_SECONDS)
        except Empty:
            continue
        if not is_stdout:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        parsed = parse_rpc_message(event)
        if isinstance(parsed, RpcResponse) and parsed.command == command and parsed.id == command_id:
            return parsed
    return None


def request_available_models(
    process: RunningProcess, timeout: float = MODEL_FETCH_TIMEOUT_SECONDS
) -> list[dict[str, Any]]:
    """Send `get_available_models` and return pi's raw `data.models` list.

    Returns `[]` on timeout / process exit / a malformed payload. Shares the
    sole-reader safety constraint of `consume_until_command_response`.
    """
    request_id = generate_id()
    send_rpc_line(process, {"type": "get_available_models", "id": request_id})
    response = consume_until_command_response(process, "get_available_models", request_id, timeout)
    if response is None or not isinstance(response.data, dict):
        return []
    models = response.data.get("models")
    if not isinstance(models, list):
        return []
    return [m for m in models if isinstance(m, dict)]


def request_state(process: RunningProcess, timeout: float = 10.0) -> dict[str, Any] | None:
    """Send `get_state` and return pi's reported `RpcSessionState` data (RPC §5.1).

    Returns None on timeout / process exit / no matching response. Shares the
    sole-reader safety constraint of `consume_until_command_response`.
    """
    request_id = generate_id()
    send_rpc_line(process, {"type": "get_state", "id": request_id})
    response = consume_until_command_response(process, "get_state", request_id, timeout)
    if response is None or not isinstance(response.data, dict):
        return None
    return response.data


def shutdown_probe_process(process: RunningProcess | None) -> None:
    """Close stdin then terminate the catalog probe's pi process.

    Pi exits on stdin EOF (Sculptor closes stdin at shutdown); terminate is
    the backstop if it lingers. Best-effort — the probe is throwaway, so any
    teardown error is logged and swallowed rather than failing the fetch.
    """
    if process is None:
        return
    try:
        process.close_stdin()
    except Exception as e:  # noqa: BLE001
        logger.debug("pi catalog probe close_stdin failed: {}", e)
    try:
        process.terminate()
    except Exception as e:  # noqa: BLE001
        logger.debug("pi catalog probe terminate failed: {}", e)


def probe_catalog(
    spawn: Callable[[Sequence[str]], RunningProcess],
    binary: str,
    session_dir: Path,
) -> tuple[list[ModelOption], ModelOption | None]:
    """Fetch + curate pi's catalog via a short-lived probe process.

    Launches a minimal `pi --mode rpc` through `spawn` against a throwaway probe
    session (a distinct `--session-id` under `session_dir`) with no extensions /
    skills / system prompt — `get_available_models` and `get_state` need none —
    issues those two RPCs as the sole reader of the process queue, then shuts the
    probe down before returning the curated `list[ModelOption]` + current
    `ModelOption | None`.

    Best-effort: on any failure (spawn error, timeout, no response) it logs and
    returns `([], None)`, never raising.
    """
    command = [
        binary,
        "--mode",
        "rpc",
        "--session-dir",
        str(session_dir),
        "--session-id",
        f"probe-{generate_id()}",
        "--no-extensions",
    ]
    probe_process = None
    try:
        probe_process = spawn(command)
        raw_models = request_available_models(probe_process)
        state = request_state(probe_process)
    except Exception as e:  # noqa: BLE001
        logger.info("pi catalog probe failed ({}); returning an empty catalog", e)
        shutdown_probe_process(probe_process)
        return [], None

    shutdown_probe_process(probe_process)

    current_raw = state.get("model") if isinstance(state, dict) else None
    current_model = model_option_from_pi(current_raw) if isinstance(current_raw, dict) else None
    options: list[ModelOption] = []
    for raw in raw_models:
        option = model_option_from_pi(raw)
        if option is not None:
            options.append(option)
    authenticated = compute_authenticated_provider_ids()
    # Drop a selected model whose provider is no longer authenticated when nothing
    # authenticated remains to fall back to: the catalog must reach its empty
    # "no usable model" state, not offer a single model that cannot run. (When an
    # authenticated model does remain, the read-only probe leaves the switch to the
    # start-time reselect in `_fetch_models_into_state`, which can `set_model`.)
    if (
        current_model is not None
        and current_model.provider not in authenticated
        and not any(option.provider in authenticated for option in options)
    ):
        current_model = None
    curated = curate_models(options, current_model, authenticated)
    if not curated and current_model is None:
        logger.info("pi catalog probe found no usable models; callers show the empty state")
        return [], None
    logger.info(
        "pi catalog probe fetched {} model(s); current model={}",
        len(curated),
        current_model.model_id if current_model is not None else None,
    )
    return curated, current_model


def _detect_pi_version_on_host(binary: str) -> str | None:
    """Run `pi --version` on the backend host and parse the version, best-effort."""
    try:
        result = run_blocking([binary, "--version"], timeout=5.0, is_checked=False)
    except Exception as e:  # noqa: BLE001
        logger.info("pi host catalog probe could not run --version ({})", e)
        return None
    # WHY: real pi emits --version to stderr, not stdout; feed both channels.
    return parse_pi_version(f"{result.stdout}\n{result.stderr}")


def _spawn_probe_on_host(command: Sequence[str]) -> RunningProcess:
    """Spawn the probe pi directly on the backend host, with the backend's env."""
    return run_background(command, env=dict(os.environ), open_stdin=True)


def probe_catalog_on_host(binary: str) -> tuple[list[ModelOption], ModelOption | None]:
    """Fetch + curate pi's catalog directly on the backend host, pre-workspace.

    The host-side twin of `PiAgent.fetch_available_models_probe`: no
    `AgentExecutionEnvironment` exists yet, so pi is spawned with the backend
    process env (which is where the api-key env vars live) against a throwaway
    session dir under Sculptor's own folder. Execution environments are local —
    same machine, same `$HOME`, same `auth.json` — so this observes the same
    catalog an in-workspace probe would. Best-effort like the core: any failure
    yields `([], None)`.

    One divergence from the in-task probe: the core keeps an UNAUTHENTICATED
    current model when an authenticated fallback exists, because a running
    agent's start-time reselect can `set_model` away from it. No reselect
    exists before a workspace does — offering that model pre-create would only
    arm the create-time provider-authentication rejection — so the host
    boundary strips the concession: the catalog is authenticated-only and the
    default re-points to the newest authenticated model.
    """
    detected_version = _detect_pi_version_on_host(binary)
    if detected_version is None or not pi_version_in_range(detected_version):
        logger.info(
            "pi host catalog probe skipped: pi version {} out of range; returning an empty catalog",
            detected_version,
        )
        return [], None
    session_dir = get_sculptor_folder() / PI_PROBE_SESSION_DIR_NAME
    available_models, default_model = probe_catalog(_spawn_probe_on_host, binary, session_dir)
    authenticated = compute_authenticated_provider_ids()
    available_models = [option for option in available_models if option.provider in authenticated]
    if default_model is not None and default_model.provider not in authenticated:
        default_model = available_models[0] if available_models else None
    return available_models, default_model
