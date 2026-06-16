"""Shared attachment handling for agent harnesses.

``ChatInputUserMessage.files`` carries the harness-agnostic upload-path
attachments the user attached in the UI. Each entry is either an absolute path
(the Electron desktop build saves uploads to a real path) or a bare upload id
stored under ``<internal>/uploads/<id>`` (the web/HTTP upload path). Before an
agent turn, these must be copied into the agent's execution environment so the
harness can deliver them to the model.

Both the Claude harness
(``ClaudeProcessManager._maybe_save_files_to_environment`` in
``agents/default/claude_code_sdk/process_manager.py``) and the pi harness
(``agents/pi_agent/prompt_assembly.py`` /  ``agent_wrapper.py``) need the same
resolution rules, so the logic lives here once rather than in two copies that
can drift. How each harness then *presents* the saved files to the model is
harness-specific and stays in the respective harness.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.utils.build import get_internal_folder


def save_attachments_to_environment(environment: AgentExecutionEnvironment, files: Sequence[str]) -> tuple[str, ...]:
    """Copy each attachment into the environment, returning the saved paths.

    An absolute path is read as-is; otherwise the entry is an upload id
    resolved under ``<internal>/uploads/``. A source that no longer exists is
    skipped (logged) rather than failing the turn.
    """
    saved_paths: list[str] = []
    for local_file_path in files:
        filename = local_file_path.split("/")[-1]
        if os.path.isabs(local_file_path):
            source = Path(local_file_path)
        else:
            source = get_internal_folder() / "uploads" / local_file_path

        try:
            file_content = source.read_bytes()
        except FileNotFoundError:
            logger.warning("Skipping missing file attachment: {}", source)
            continue

        destination = environment.get_attachments_path() / filename
        environment.write_file(path=str(destination), content=file_content, mode="wb")
        saved_paths.append(str(destination))

    return tuple(saved_paths)
