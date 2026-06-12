"""Integration tests for file chips inside tool blocks (Read, Glob) in the alpha chat view.

Read and Glob tool calls reference files. These tests verify that the alpha view
renders file-path chips inside the corresponding tool blocks so users can see at
a glance which files the agent touched.

Scenario 1 (multiple sequential reads + glob):
  The agent reads several files and runs a glob, each as a separate tool call.

Scenario 2 (background bash + read of output file):
  The agent runs a bash command in the background, then reads the output file.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# ---------------------------------------------------------------------------
# Prompt for test 1: multiple sequential Read + Glob calls
# ---------------------------------------------------------------------------
MULTI_READ_AND_GLOB_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "src/app.ts",
        "content": "export const app = () => console.log('hello');\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "src/utils.ts",
        "content": "export const add = (a: number, b: number) => a + b;\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "README.md",
        "content": "# Test Project\\nA test project.\\n"
      }
    },
    {
      "command": "read_file",
      "args": {
        "file_path": "src/app.ts",
        "limit": 50
      }
    },
    {
      "command": "read_file",
      "args": {
        "file_path": "src/utils.ts",
        "limit": 50
      }
    },
    {
      "command": "read_file",
      "args": {
        "file_path": "README.md",
        "limit": 50
      }
    },
    {
      "command": "glob",
      "args": {
        "pattern": "src/*.ts"
      }
    },
    {
      "command": "read_file",
      "args": {
        "file_path": "src/app.ts",
        "limit": 50
      }
    }
  ]
}`"""


# ---------------------------------------------------------------------------
# Prompt for test 2: background bash then read the output file
# ---------------------------------------------------------------------------
BACKGROUND_BASH_THEN_READ_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "output.log",
        "content": "line1\\nline2\\nline3\\nline4\\nline5\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "cat output.log"
      }
    },
    {
      "command": "read_file",
      "args": {
        "file_path": "output.log"
      }
    }
  ]
}`"""


@user_story("to see file chips on Read tool blocks in the alpha view")
def test_read_and_glob_tool_blocks_show_file_chips(sculptor_instance_: SculptorInstance) -> None:
    """Multiple Read and Glob tool calls each show file-path chips in their tool blocks."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=MULTI_READ_AND_GLOB_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # TODO: Add assertions for file chips on Read/Glob tool blocks


@user_story("to see file chips on Read tool blocks after a bash command")
def test_bash_then_read_shows_file_chip(sculptor_instance_: SculptorInstance) -> None:
    """A bash command followed by a Read of the output file shows both a bash block and a file chip."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=BACKGROUND_BASH_THEN_READ_PROMPT,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    alpha_view = get_alpha_chat_view(page)
    expect(alpha_view).to_be_visible()

    # TODO: Add assertions for bash block + file chip on Read tool block
