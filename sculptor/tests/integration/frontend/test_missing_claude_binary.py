"""Integration test for ClaudeBinaryNotFoundError.

Scenario: Claude was installed when the app first loaded (onboarding passed),
but the binary was deleted while the app was running.  Sending a message
should surface "Claude Not Available" + "Go to Settings" instead of a raw
traceback.

Setup strategy
--------------
1. Use create_claude_stub_dir() to create a stub "claude" that reports a
   valid version so that the dependency check at startup passes and the
   onboarding wizard lets the app through.
2. Write the stub's absolute path into the config as
   ``dependency_paths.claude`` so the server resolves the binary directly
   (avoids PATH manipulation that can be fragile in CI).
3. Start the Sculptor instance (stub present → installed=True at mount time).
4. Create a workspace using the real Claude Opus model but WITHOUT a prompt
   yet, while the stub is still alive (the workspace creation flow may
   perform a full page reload which would re-trigger RequireOnboarding).
5. Delete the stub binary.  We are now on the task page — no more full
   page reloads expected.
6. Send a chat message.  The model is Claude Opus (not FAKE_CLAUDE), so
   _is_fake_claude=False and _resolve_claude_binary_path() is called.
   shutil.which(absolute_path) returns None → ClaudeBinaryNotFoundError.
"""

from pathlib import Path

from playwright.sync_api import expect

from imbue_core.sculptor.user_config import DependencyPaths
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.dependency_stubs import create_claude_stub_dir
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# Long name shown in the model selector for the real Claude Opus model.
_CLAUDE_OPUS_MODEL_NAME = "Claude 4.7 Opus"


def _setup_removable_claude_stub(factory: SculptorInstanceFactory, tmp_path: Path) -> Path:
    """Prepare the factory and return a path to the stub binary.

    Creates a stub that passes the version check, then writes the stub's
    absolute path into the config as ``dependency_paths.claude``.  This
    makes the dependency service use CUSTOM mode with that exact path,
    and deleting the stub file makes ``shutil.which(absolute_path)``
    return ``None``.
    """
    stub_dir = create_claude_stub_dir(tmp_path)
    stub_path = stub_dir / "claude"

    # Write the absolute stub path into the config so the server resolves
    # it directly.  We update the config file that the factory already
    # created (via the default sculptor folder populator).
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    updated_config = config.model_copy(update={"dependency_paths": DependencyPaths(claude=str(stub_path))})
    save_config(updated_config, config_path)

    return stub_path


@user_story("to see a helpful error when the Claude binary disappears after initial setup")
def test_missing_claude_binary_shows_friendly_error(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """When Claude is present at startup (dependency check passes) but then
    goes missing before a message is sent, the error block should show
    'Claude Not Available' with a 'Go to Settings' link instead of a raw
    exception traceback."""
    claude_stub = _setup_removable_claude_stub(sculptor_instance_factory_, tmp_path)

    with sculptor_instance_factory_.spawn_instance() as instance:
        # Stub exists: RequireOnboarding.tsx runs its one-time mount check,
        # sees installed=True, and lets the app through.

        # Create the workspace with the real Opus model but WITHOUT a prompt.
        # We must NOT delete the stub yet: open_new_workspace_modal may
        # trigger a full page reload which would re-trigger RequireOnboarding.
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            prompt="",  # no message yet
            model_name=_CLAUDE_OPUS_MODEL_NAME,
        )

        # We are now on the task page. No more full page reloads expected.
        # Delete the stub to simulate Claude being removed after setup.
        claude_stub.unlink()

        # Send a chat message. The workspace model is Claude Opus (not
        # FAKE_CLAUDE), so _is_fake_claude=False and
        # _resolve_claude_binary_path() is called. shutil.which returns None
        # → ClaudeBinaryNotFoundError is raised and caught by the agent wrapper.
        chat_panel = task_page.get_chat_panel()
        send_chat_message(chat_panel, "Hello")

        error_block = chat_panel.get_error_block()
        expect(error_block).to_be_visible()

        # It should show our friendly label, not a raw exception class name.
        expect(error_block).to_contain_text("Claude Not Available")

        # It should include the error message from ClaudeBinaryNotFoundError.
        expect(error_block).to_contain_text("Claude binary not found")

        # It should have a settings link — not a retry button.
        expect(error_block).to_contain_text("Go to Settings")
        retry_button = chat_panel.get_error_block_retry_button()
        expect(retry_button).to_have_count(0)

        # The thinking indicator should be gone (agent finished with error).
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible()
