"""Integration tests for the entity picker's third-level workspace drill.

The entity picker drilled in from the ``+`` prefilter has three navigation
states (``EntityMentionList.tsx``):

  1. Top — when pinned to a type (``workspace``), workspace rows are visible.
  2. Workspace-drilled — Tab/ArrowRight or a mouse click on a workspace row
     narrows the list to that workspace's agents only. Enter commits the
     workspace itself. (Mouse parity with the keyboard drill is SCU-1296: a
     workspace row carries a drill-in chevron, so clicking it opens the next
     level rather than committing the workspace.)
  3. Step-back — Shift+Tab pops one drill level.

``test_mention_picker_completion.py`` only exercises commit-the-workspace; the
``Tab`` drill into a workspace and the resulting agent-only list have no
end-to-end coverage. The behavior is unit-tested in
``EntityMentionList.test.tsx`` against a fixed item array, but a silent
regression in the drill state machine inside the live editor (e.g. clearQuery
firing a stale items refresh, the suggestion-config command swallowing the
drill action) would not be caught.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.entity_picker import PlaywrightEntityPickerElement
from sculptor.testing.elements.entity_picker import open_workspace_entity_drill
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.user_config import enable_entity_mentions
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Each test creates a workspace with a unique name so the entity-picker
# filter step ("type the workspace name to narrow to a single row") doesn't
# depend on what the shared sculptor_instance fixture left in the database.
# A short ASCII suffix keeps the name typable through ``press_sequentially``.
_WORKSPACE_NAME_PREFIX = "WsDrill"


def _navigate_to_task_chat(sculptor_instance: SculptorInstance, workspace_name: str) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
        workspace_name=workspace_name,
    )


def _open_workspace_drill_state(page: Page, chat_input: Locator, workspace_name: str) -> None:
    """Open the ``+`` picker, drill into Workspaces, and filter to ``workspace_name``.

    Leaves the picker in pinnedType=workspace mode with exactly one row
    matching ``workspace_name`` so the next Tab unambiguously drills into
    that one workspace.
    """
    entity_items = open_workspace_entity_drill(page, chat_input)

    # Type slowly (matching ``insert_workspace_entity_mention``) so each
    # keystroke gets a full transaction + items() refresh before the next, and
    # wait for the filter to settle to the single matching row before the
    # caller drills further.
    chat_input.press_sequentially(workspace_name, delay=30)
    expect(entity_items).to_have_count(1)


@user_story("to drill into a workspace from the entity picker and see only its agents")
def test_tab_on_workspace_drills_into_agent_list(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Tab on a workspace row narrows the entity list to that workspace's agents.

    This is the third level of the picker's drill chain: from the pinned
    Workspaces list, Tab on the workspace row hides the workspace itself and
    surfaces only the agents whose ``parentId`` matches the drilled workspace.
    Adds a second agent before drilling so the post-drill list has two
    distinct rows — that's how we tell "drilled into agents" apart from "still
    on the workspace row" without depending on row text content.
    """
    page = sculptor_instance_.page
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)

    workspace_name = f"{_WORKSPACE_NAME_PREFIX}TabAgents"
    task_page = _navigate_to_task_chat(sculptor_instance_, workspace_name)
    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    create_agent_panel(page, section="center")
    expect(PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()).to_have_count(2)

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    _open_workspace_drill_state(page, chat_input, workspace_name)

    entity_picker = PlaywrightEntityPickerElement(page)
    entity_items = entity_picker.get_entity_items()

    page.keyboard.press("Tab")

    expect(entity_items).to_have_count(2)


@user_story("to drill into a workspace by clicking it with the mouse in the entity picker")
def test_click_on_workspace_drills_into_agent_list(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Clicking a workspace row narrows the entity list to that workspace's agents.

    SCU-1296: the mouse must reach the agent sub-list the same way the keyboard
    does. A workspace row carries a drill-in chevron, so a click opens the next
    level (its agents) instead of committing the workspace itself — mirroring
    Tab/ArrowRight. Adds a second agent before drilling so the post-drill list
    has two distinct rows; that's how we tell "drilled into agents" apart from
    "still on the workspace row" (or "committed and closed") without depending
    on row text content.
    """
    page = sculptor_instance_.page
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)

    workspace_name = f"{_WORKSPACE_NAME_PREFIX}ClickAgents"
    task_page = _navigate_to_task_chat(sculptor_instance_, workspace_name)
    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    create_agent_panel(page, section="center")
    expect(PlaywrightPanelTabElement(page, sub_section="center").get_panel_tabs()).to_have_count(2)

    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    _open_workspace_drill_state(page, chat_input, workspace_name)

    entity_picker = PlaywrightEntityPickerElement(page)
    entity_items = entity_picker.get_entity_items()

    # The drill state leaves exactly one workspace row visible. Click it.
    expect(entity_items).to_have_count(1)
    entity_items.first.click()

    # Clicking the workspace drilled in: the list now shows only that
    # workspace's two agents, not the workspace row (which would have stayed at
    # count 1) and not a committed-and-closed picker (which would be count 0).
    expect(entity_items).to_have_count(2)


@user_story("to step back to the workspace list with Shift+Tab after drilling in")
def test_shift_tab_steps_back_from_workspace_drill(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Shift+Tab from a workspace-drilled state pops back to the workspace list.

    Each drill level must be popable independently (workspace-drill → top of
    pinned picker → parent ``+`` picker). This test only verifies the first
    pop — we land back on the workspace row with the workspace's chevron
    showing, not the agent list.
    """
    page = sculptor_instance_.page
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)

    workspace_name = f"{_WORKSPACE_NAME_PREFIX}StepBack"
    task_page = _navigate_to_task_chat(sculptor_instance_, workspace_name)
    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    _open_workspace_drill_state(page, chat_input, workspace_name)

    entity_picker = PlaywrightEntityPickerElement(page)
    entity_items = entity_picker.get_entity_items()

    page.keyboard.press("Tab")
    expect(entity_items).to_have_count(1)

    page.keyboard.down("Shift")
    page.keyboard.press("Tab")
    page.keyboard.up("Shift")

    expect(entity_picker.get_entity_list()).to_be_visible()
    expect(entity_items.first).to_be_visible()


@user_story("to commit an agent as an entity-mention chip from a drilled workspace")
def test_enter_on_agent_after_drill_commits_agent_chip(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Enter on an agent row inside a drilled workspace inserts an agent chip.

    Verifies the full third-level commit path:
      ``+wor`` -> Enter -> filter -> Tab -> Enter -> chip with type=agent.
    The chip carries ``data-entity-type="agent"`` (set by ``MentionChip.tsx``
    via the entity TipTap node attrs) so the type is observable without
    relying on row text content.
    """
    page = sculptor_instance_.page
    enable_entity_mentions(page, backend_url=sculptor_instance_.backend_api_url)

    workspace_name = f"{_WORKSPACE_NAME_PREFIX}AgentCommit"
    task_page = _navigate_to_task_chat(sculptor_instance_, workspace_name)
    chat_input = task_page.get_chat_panel().get_chat_input()
    expect(chat_input).to_be_visible()

    _open_workspace_drill_state(page, chat_input, workspace_name)

    page.keyboard.press("Tab")

    entity_picker = PlaywrightEntityPickerElement(page)
    expect(entity_picker.get_entity_items().first).to_be_visible()

    chat_input.press("Enter")

    chat_panel = task_page.get_chat_panel()
    entity_chip = chat_panel.get_entity_mention_chips()
    expect(entity_chip).to_be_visible()
    expect(entity_chip).to_have_attribute("data-entity-type", "agent")
