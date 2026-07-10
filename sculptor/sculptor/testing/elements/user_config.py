"""Helpers for toggling user config flags via the API in integration tests.

Each helper does a GET + PUT + reload against ``/api/v1/config`` rather than
driving the settings UI, which has timing issues with Radix controls.

The requests target the backend's HTTP origin resolved via
:func:`resolve_backend_api_url`, not ``page.url``: in packaged Electron builds
the renderer origin is ``sculptor://app`` (which serves no ``/api`` and which
Playwright's ``page.request`` cannot fetch), while the backend runs on a
separate http origin.
"""

from playwright.sync_api import Page

from sculptor.testing.backend_url import resolve_backend_api_url
from sculptor.testing.elements.base import wait_for_tiptap_ready

# Under heavy load the backend can transiently return 500 (e.g. SQLite busy),
# so the config PUT is retried a few times with a short delay between attempts.
_PUT_RETRY_COUNT = 3
_PUT_RETRY_DELAY_MS = 500


def _set_user_config_flag(page: Page, field: str, value: object) -> None:
    """Set a single field on the user config via the REST API, then reload.

    This is more reliable than toggling through the settings UI, which has
    timing issues with Radix controls.
    """
    base_url = resolve_backend_api_url(page)
    config_url = f"{base_url}/api/v1/config"

    response = page.request.get(config_url)
    assert response.ok, f"GET /api/v1/config failed: {response.status}"
    current_config = response.json()

    current_config[field] = value
    for _attempt in range(_PUT_RETRY_COUNT):
        put_response = page.request.put(config_url, data={"userConfig": current_config})
        if put_response.ok:
            break
        page.wait_for_timeout(_PUT_RETRY_DELAY_MS)
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


def enable_default_fast_mode(page: Page) -> None:
    """Enable the default-fast-mode user preference."""
    _set_user_config_flag(page, "defaultFastMode", True)
