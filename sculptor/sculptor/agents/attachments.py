"""Shared attachment handling for agent harnesses.

``ChatInputUserMessage.files`` carries the harness-agnostic upload-path
attachments the user attached in the UI. Each entry is either an absolute path
(the Electron desktop build saves uploads to a real path) or a bare upload id
stored under ``<internal>/uploads/<id>`` (the web/HTTP upload path). Before an
agent turn, these must be copied into the agent's execution environment so the
harness can deliver them to the model.

The Claude harness (``ClaudeProcessManager._maybe_save_files_to_environment``
in ``agents/default/claude_code_sdk/process_manager.py``), the pi harness
(``agents/pi_agent/prompt_assembly.py`` /  ``agent_wrapper.py``), and the
task-deletion cleanup (``web/app.py``) all need the same way of mapping an
attachment reference back to its source on disk, so ``resolve_attachment_source``
lives here once rather than in copies that can drift. How each harness then
*presents* the saved files to the model is harness-specific and stays in the
respective harness.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.utils.build import get_internal_folder


def resolve_attachment_source(local_file_path: str) -> Path:
    """Map an attachment reference to its source path on disk.

    An absolute path (the Electron desktop build's saved upload) is returned
    as-is; otherwise the entry is an upload id stored under
    ``<internal>/uploads/`` (the web/HTTP upload path).
    """
    local_path = Path(local_file_path)
    if local_path.is_absolute():
        return local_path
    return get_internal_folder() / "uploads" / local_file_path


def save_attachments_to_environment(environment: AgentExecutionEnvironment, files: Sequence[str]) -> tuple[str, ...]:
    """Copy each attachment into the environment, returning the saved paths.

    An absolute path is read as-is; otherwise the entry is an upload id
    resolved under ``<internal>/uploads/``. A source that no longer exists is
    skipped (logged) rather than failing the turn.
    """
    saved_paths: list[str] = []
    for local_file_path in files:
        source = resolve_attachment_source(local_file_path)
        filename = Path(local_file_path).name

        try:
            file_content = source.read_bytes()
        except FileNotFoundError:
            logger.warning("Skipping missing file attachment: {}", source)
            continue

        destination = environment.get_attachments_path() / filename
        environment.write_file(path=str(destination), content=file_content, mode="wb")
        saved_paths.append(str(destination))

    return tuple(saved_paths)
