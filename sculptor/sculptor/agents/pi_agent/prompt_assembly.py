"""Prompt assembly for the pi harness — files and images on the `prompt` command.

`ChatInputUserMessage.files` carries the harness-agnostic upload-path
attachments. Pi delivers them two ways, split exclusively by type:

- **Images** (the formats the upload pipeline accepts) ride inline on the
  `prompt` command's documented `images: ImageContent[]` field as base64 +
  mimeType (RPC §4; `ImageContent` is
  `{"type":"image","data":"<base64>","mimeType":"image/png"}`).
- **Everything else** is presented as file paths in the prompt text, the same
  way Claude's prompt assembly presents them — pi reads the contents with its
  own `read` tool (`supports_file_references` already proves that loop).

The file-saving step mirrors Claude's
`ClaudeProcessManager._maybe_save_files_to_environment`
(`agents/default/claude_code_sdk/process_manager.py`): same resolution rules
(absolute path, or `<internal>/uploads/<id>`), same destination
(`environment.get_attachments_path()`), same skip-on-missing-source.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Sequence
from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.utils.build import get_internal_folder

# The image formats the upload pipeline accepts, mapped to the mimeType pi's
# `ImageContent` block needs. Python mirror of the frontend's notion of an
# image (`ALLOWED_EXTENSIONS` / `ALLOWED_MIME_TYPES` in
# `frontend/src/components/FileUploadUtils.ts`); keep the two in sync.
IMAGE_EXTENSION_TO_MIME_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


def is_image_attachment(path: str) -> bool:
    """True when `path` is one of the image formats the upload pipeline accepts."""
    return Path(path).suffix.lower() in IMAGE_EXTENSION_TO_MIME_TYPE


def image_mime_type(path: str) -> str:
    """The `ImageContent.mimeType` for an image path. Call only on images."""
    return IMAGE_EXTENSION_TO_MIME_TYPE[Path(path).suffix.lower()]


def save_attachments_to_environment(environment: AgentExecutionEnvironment, files: Sequence[str]) -> tuple[str, ...]:
    """Copy each attachment into the environment, returning the saved paths.

    Mirrors Claude's `_maybe_save_files_to_environment`: an absolute path is
    used as-is, otherwise the entry is an upload id resolved under
    `<internal>/uploads/`. A missing source is skipped rather than failing the turn.
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
            logger.info("Skipping missing file attachment: {}", source)
            continue

        destination = environment.get_attachments_path() / filename
        environment.write_file(path=str(destination), content=file_content, mode="wb")
        saved_paths.append(str(destination))

    return tuple(saved_paths)


def split_image_and_path_attachments(saved_paths: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Partition saved attachment paths into (images, non-images).

    Exclusive by construction: a file is never both an `images[]` entry and a
    prompt-text path.
    """
    images = tuple(path for path in saved_paths if is_image_attachment(path))
    others = tuple(path for path in saved_paths if not is_image_attachment(path))
    return images, others


def build_image_block(path: str, data: bytes) -> dict[str, str]:
    """Encode one image attachment into pi's `ImageContent` block."""
    encoded = base64.b64encode(data).decode("ascii")
    mime_type = image_mime_type(path)
    # Base64 inflates payloads ~33%, so a multi-MB image becomes a multi-MB
    # stdin line; log the encoded size at debug to trace that.
    logger.debug("PiAgent encoding image attachment {} ({} base64 chars, mimeType={})", path, len(encoded), mime_type)
    return {"type": "image", "data": encoded, "mimeType": mime_type}


def build_attachment_instructions(file_paths: Sequence[str]) -> str:
    """Render non-image attachment paths into prompt-text instructions.

    Mirrors the file-attachment block Claude's `get_user_instructions`
    prepends (`agents/default/claude_code_sdk/process_manager_utils.py`) so the
    two harnesses present attached paths identically. Empty when there are no
    path attachments.
    """
    if not file_paths:
        return ""
    file_paths_str = "\n- ".join(file_paths)
    return f"""<system-instructions>
The user has attached these files. Read them before proceeding.
{file_paths_str}
</system-instructions>

"""
