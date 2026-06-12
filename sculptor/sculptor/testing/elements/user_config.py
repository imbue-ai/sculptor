"""Helpers for toggling user config flags via the API in integration tests.

Follows the same GET + PUT + reload pattern as ``_set_chat_view_alpha`` in
``alpha_chat_view.py``.
"""

from playwright.sync_api import Page

from sculptor.testing.elements.base import wait_for_tiptap_ready


def _set_user_config_flag(page: Page, field: str, value: object) -> None:
    """Set a single field on the user config via the REST API, then reload.

    This is more reliable than toggling through the settings UI, which has
    timing issues with Radix controls.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    config_url = f"{base_url}/api/v1/config"

    response = page.request.get(config_url)
    assert response.ok, f"GET /api/v1/config failed: {response.status}"
    current_config = response.json()

    current_config[field] = value
    # Retry the PUT — under heavy load the backend can transiently return 500
    # (e.g. SQLite busy), matching the retry in _set_chat_view_alpha.
    for _attempt in range(3):
        put_response = page.request.put(config_url, data={"userConfig": current_config})
        if put_response.ok:
            break
        page.wait_for_timeout(500)
    assert put_response.ok, f"PUT /api/v1/config failed: {put_response.status}"

    page.reload()
    page.wait_for_load_state("networkidle")

    # Wait for Tiptap to re-initialize after reload (if on a workspace page).
    wait_for_tiptap_ready(page)


def enable_in_place_workspaces(page: Page) -> None:
    """Enable the experimental in-place workspaces flag."""
    _set_user_config_flag(page, "enableInPlaceWorkspaces", True)


def enable_clone_workspaces(page: Page) -> None:
    """Enable the opt-in clone workspaces flag.

    Worktree mode is the default; clone mode is gated behind this flag so it
    only appears in the Add Workspace mode selector for users who want it.
    """
    _set_user_config_flag(page, "enableCloneWorkspaces", True)


def enable_entity_mentions(page: Page) -> None:
    """Enable the experimental entity mentions flag."""
    _set_user_config_flag(page, "enableEntityMentions", True)


def enable_pi_agent(page: Page) -> None:
    """Enable the experimental pi-agent flag.

    Gates the pi option in the agent-type pickers; off by default, so any
    test that selects pi (or asserts the option is visible) must enable it first.
    """
    _set_user_config_flag(page, "enablePiAgent", True)


def disable_pi_agent(page: Page) -> None:
    """Disable the experimental pi-agent flag (its default).

    `enable_pi_agent` (also called by `start_task_and_wait_for_ready`
    whenever a harness is selected) is sticky on the shared test instance, so a
    test that asserts the flag-off behavior must reset it defensively first.
    """
    _set_user_config_flag(page, "enablePiAgent", False)


def enable_default_fast_mode(page: Page) -> None:
    """Enable the default-fast-mode user preference."""
    _set_user_config_flag(page, "defaultFastMode", True)
