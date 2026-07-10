"""Tests for the shared pi catalog probe: the spawn-agnostic core and the host-side entry."""

import json
from pathlib import Path
from queue import Queue
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch

from sculptor.agents.pi_agent.catalog_probe import PI_PROBE_SESSION_DIR_NAME
from sculptor.agents.pi_agent.catalog_probe import probe_catalog
from sculptor.agents.pi_agent.catalog_probe import probe_catalog_on_host
from sculptor.services.dependency_management_service import PI_VERSION_RANGE

_RAW_MODELS: list[dict[str, Any]] = [
    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"},
    {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5", "provider": "anthropic"},
    {"id": "gpt-5", "name": "GPT-5", "provider": "openai"},
]


def _event(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


def _models_response(raw_models: list[dict[str, Any]]) -> str:
    return _event(
        {
            "type": "response",
            "command": "get_available_models",
            "success": True,
            "id": "cmd-models",
            "data": {"models": raw_models},
        }
    )


def _state_response_with_model(model: dict[str, Any] | None) -> str:
    return _event(
        {
            "type": "response",
            "command": "get_state",
            "success": True,
            "id": "cmd-state",
            "data": {"sessionId": "s", "messageCount": 1, "model": model},
        }
    )


def _make_process(lines: list[str]) -> MagicMock:
    """Stub `RunningProcess`: replays canned stdout lines then reports finished."""
    queue: Queue[tuple[str, bool]] = Queue()
    for line in lines:
        queue.put((line, True))

    process = MagicMock()
    process.get_queue.return_value = queue
    # is_finished() is polled inside the consume loop; report True only once
    # the queue has been drained.
    process.is_finished.side_effect = [False] * len(lines) + [True] * 50
    return process


class TestProbeCatalog:
    """The spawn-agnostic probe core."""

    def test_returns_curated_catalog_and_current_model(self) -> None:
        """The probe fetches models + state through the two RPCs, applies the
        authenticated filter, and shuts its process down."""
        process = _make_process(
            [
                _models_response(_RAW_MODELS),
                _state_response_with_model(
                    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
                ),
            ]
        )
        spawn = MagicMock(return_value=process)
        with (
            patch(
                "sculptor.agents.pi_agent.catalog_probe.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.compute_authenticated_provider_ids",
                return_value={"anthropic"},
            ),
        ):
            available_models, current_model = probe_catalog(spawn, "/bin/pi", Path("/fake/probe"))

        # openai is unauthenticated so gpt-5 is filtered; newest-first sort.
        assert [option.model_id for option in available_models] == ["claude-opus-4-8", "claude-sonnet-4-5"]
        assert current_model is not None and current_model.model_id == "claude-opus-4-8"
        command = list(spawn.call_args.args[0])
        assert command[:3] == ["/bin/pi", "--mode", "rpc"]
        assert command[command.index("--session-dir") + 1] == str(Path("/fake/probe"))
        assert command[command.index("--session-id") + 1] == "probe-probe-sess"
        assert "--no-extensions" in command
        process.close_stdin.assert_called_once()
        process.terminate.assert_called_once()

    def test_spawn_failure_returns_empty_catalog(self) -> None:
        """A spawn failure is best-effort: an empty catalog, never an exception."""
        spawn = MagicMock(side_effect=OSError("no such binary"))
        assert probe_catalog(spawn, "/bin/pi", Path("/fake/probe")) == ([], None)

    def test_drops_unauthenticated_current_model_without_fallback(self) -> None:
        """A selected model whose provider lost authentication is dropped when nothing
        authenticated remains, so the catalog reaches its designed empty state."""
        raw = [{"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}]
        process = _make_process(
            [
                _models_response(raw),
                _state_response_with_model({"id": "openai/gpt-4o", "name": "GPT-4o", "provider": "openrouter"}),
            ]
        )
        spawn = MagicMock(return_value=process)
        with (
            patch(
                "sculptor.agents.pi_agent.catalog_probe.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.compute_authenticated_provider_ids",
                return_value=set(),
            ),
        ):
            assert probe_catalog(spawn, "/bin/pi", Path("/fake/probe")) == ([], None)


class TestProbeCatalogOnHost:
    """The host-side entry: version gate + host spawn, no AgentExecutionEnvironment."""

    def test_version_mismatch_returns_empty_without_spawning(self) -> None:
        with (
            patch(
                "sculptor.agents.pi_agent.catalog_probe._detect_pi_version_on_host",
                return_value="0.1.0",
            ),
            patch("sculptor.agents.pi_agent.catalog_probe.run_background") as run_background_mock,
        ):
            assert probe_catalog_on_host("/bin/pi") == ([], None)
        run_background_mock.assert_not_called()

    def test_spawns_probe_on_host_with_backend_env(self, tmp_path: Path) -> None:
        """The host probe runs pi with the backend process env, stdin open, against a
        throwaway session dir under Sculptor's own folder."""
        process = _make_process(
            [
                _models_response(_RAW_MODELS),
                _state_response_with_model(
                    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
                ),
            ]
        )
        with (
            patch(
                "sculptor.agents.pi_agent.catalog_probe._detect_pi_version_on_host",
                return_value=PI_VERSION_RANGE.recommended_version,
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.run_background",
                return_value=process,
            ) as run_background_mock,
            patch(
                "sculptor.agents.pi_agent.catalog_probe.get_sculptor_folder",
                return_value=tmp_path,
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.compute_authenticated_provider_ids",
                return_value={"anthropic"},
            ),
        ):
            available_models, current_model = probe_catalog_on_host("/bin/pi")

        assert [option.model_id for option in available_models] == ["claude-opus-4-8", "claude-sonnet-4-5"]
        assert current_model is not None and current_model.model_id == "claude-opus-4-8"
        command = list(run_background_mock.call_args.args[0])
        assert command[command.index("--session-dir") + 1] == str(tmp_path / PI_PROBE_SESSION_DIR_NAME)
        kwargs = run_background_mock.call_args.kwargs
        assert kwargs["open_stdin"] is True
        # The backend process env rides along so pi resolves providers the same
        # way an in-workspace probe would.
        assert "PATH" in kwargs["env"]

    def test_strips_unauthenticated_current_model_kept_for_in_task_reselect(self, tmp_path: Path) -> None:
        """An unauthenticated session default never reaches a pre-create surface.

        The core probe deliberately KEEPS an unauthenticated current model when an
        authenticated fallback exists — in-task, the start-time reselect can
        `set_model` away from it. No reselect exists before a workspace does, so
        offering that model in the modal/CLI would only arm the create-time 422.
        The host boundary strips the concession: the catalog is authenticated-only
        and the default re-points to the newest authenticated model.
        """
        raw = [
            {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"},
            {"id": "gpt-5", "name": "GPT-5", "provider": "openai"},
        ]
        # pi's session default is the anthropic model, but only openai is authenticated.
        process = _make_process(
            [
                _models_response(raw),
                _state_response_with_model(
                    {"id": "claude-opus-4-8", "name": "Claude Opus 4.8", "provider": "anthropic"}
                ),
            ]
        )
        with (
            patch(
                "sculptor.agents.pi_agent.catalog_probe._detect_pi_version_on_host",
                return_value=PI_VERSION_RANGE.recommended_version,
            ),
            patch("sculptor.agents.pi_agent.catalog_probe.run_background", return_value=process),
            patch("sculptor.agents.pi_agent.catalog_probe.get_sculptor_folder", return_value=tmp_path),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.generate_id",
                side_effect=["probe-sess", "cmd-models", "cmd-state"],
            ),
            patch(
                "sculptor.agents.pi_agent.catalog_probe.compute_authenticated_provider_ids",
                return_value={"openai"},
            ),
        ):
            available_models, default_model = probe_catalog_on_host("/bin/pi")

        assert [option.model_id for option in available_models] == ["gpt-5"]
        assert default_model is not None and default_model.model_id == "gpt-5"
