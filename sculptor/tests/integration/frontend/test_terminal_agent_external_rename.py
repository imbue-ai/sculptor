"""Integration test for live propagation of an external terminal-agent rename.

Regression test for SCU-1531: renaming a terminal agent via the ``sculpt`` CLI
(which hits ``PATCH /api/v1/workspaces/{workspace_id}/agents/{agent_id}``)
looked like a no-op in the UI. The new name only appeared after the user
switched tabs, which forced a re-fetch of the agent list.

The cause was server-side: the rename endpoint persisted the new title but
never broadcast a task update to live WebSocket subscribers. Coding agents
masked the bug because their constant message activity piggybacks the fresh
title onto the next broadcast; an idle terminal agent ("no message-queue
subscription, no title generation") never re-broadcasts, so its tab stayed
stale until a tab switch.

This test reproduces the external rename faithfully by issuing the PATCH the
CLI issues and asserting the tab label updates live, with NO tab switch.

The terminal agent is driven to a fully idle state (a shell round-trip) BEFORE
the rename: its one startup task message (``EnvironmentAcquiredRunnerMessage``)
has already been published by then, so an idle terminal produces no further
broadcast that could accidentally carry the new title and mask the bug.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.foundation.itertools import only
from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import run_command_in_agent_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A registered terminal agent whose launch command announces readiness then
# falls through to an idle login shell. The bare "terminal" agent type was
# removed (Decision B2); a registered agent — the model the bundled Claude CLI
# agent uses — exercises the same idle-terminal rename path.
_IDLE_TERM_LAUNCH = "echo idle-term-ready"


def _create_terminal_agent(agent_tab_bar: PlaywrightAgentTabBarElement) -> None:
    agent_tab_bar.open_agent_type_menu()
    agent_tab_bar.get_agent_type_menu_item_registered("idle-term").click()


def _drive_terminal_to_idle(page: Page) -> None:
    """Wait until the terminal's shell is up and responsive, then idle.

    A successful shell round-trip proves the backend acquired the environment
    (so the one-shot ``EnvironmentAcquiredRunnerMessage`` task publish has
    already happened) and the PTY is live. After this the terminal agent emits
    no further task updates, so a later rename's broadcast — or its absence —
    is observed in isolation.
    """
    expect(get_agent_terminal_textarea(page)).to_be_attached()
    page.wait_for_timeout(3_000)
    run_command_in_agent_terminal(page, "echo terminal-ready-marker")
    wait_for_xterm_substring(page, "terminal-ready-marker")


@user_story("to see a terminal agent's tab update live when it is renamed via sculpt")
def test_terminal_agent_external_rename_updates_tab_live(
    sculptor_instance_: SculptorInstance,
) -> None:
    """An external (sculpt/API) rename of a terminal agent updates its tab live.

    Steps:
    1. Create a workspace with a chat agent, then add a terminal agent and
       drive it to a fully idle state.
    2. Resolve the workspace and terminal-agent IDs via the backend API.
    3. Rename the terminal agent with a direct PATCH (as `sculpt agent rename`
       does), without switching tabs.
    4. Verify the terminal tab's label updates live to the new name.
    """
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="Say hello", workspace_name="External Rename WS")
    agent_tab_bar = PlaywrightAgentTabBarElement(page)
    agent_tabs = agent_tab_bar.get_agent_tabs()
    expect(agent_tabs).to_have_count(1)

    registrations_dir = sculptor_instance_.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    (registrations_dir / "idle-term.toml").write_text(
        f'display_name = "Idle Term"\nlaunch_command = "{_IDLE_TERM_LAUNCH}"\n'
    )

    # Step 1: Add a registered terminal agent. It is created second, so it is the
    # tab at index 1 and is labeled "Idle Term 1". Drive it to idle so its
    # startup task message can't mask the rename broadcast.
    _create_terminal_agent(agent_tab_bar)
    expect(agent_tabs).to_have_count(2)
    terminal_tab = agent_tabs.nth(1)
    expect(terminal_tab).to_have_text("Idle Term 1")
    _drive_terminal_to_idle(page)

    # Step 2: Resolve the workspace and terminal-agent IDs via the backend API,
    # exactly as the sculpt CLI does (list workspaces, then list agents).
    base_url = sculptor_instance_.backend_api_url.rstrip("/")
    workspaces = page.request.get(f"{base_url}/api/v1/workspaces/recent").json()["workspaces"]
    workspace_id = only(ws["objectId"] for ws in workspaces if not ws.get("isDeleted"))
    agents = page.request.get(f"{base_url}/api/v1/workspaces/{workspace_id}/agents").json()
    terminal_agent_id = only(agent["id"] for agent in agents if agent["title"] == "Idle Term 1")

    # Step 3: Rename the terminal agent with the same PATCH `sculpt agent
    # rename` issues. We deliberately do NOT switch tabs afterward: the only way
    # the UI can learn the new name is a live broadcast from the server.
    response = page.request.patch(
        f"{base_url}/api/v1/workspaces/{workspace_id}/agents/{terminal_agent_id}",
        data={"title": "Renamed By Sculpt"},
    )
    assert response.ok, f"rename request failed: {response.status} {response.text()}"

    # Step 4: The tab label must update live, without a tab switch forcing a
    # re-fetch.
    expect(terminal_tab).to_have_text("Renamed By Sculpt")
