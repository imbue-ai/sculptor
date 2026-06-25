from __future__ import annotations

import itertools
import json
import re
from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
from typing import TypeVar

import playwright
from loguru import logger
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect
from tenacity import RetryError
from tenacity import retry
from tenacity import retry_if_exception
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from sculptor.constants import ElementIDs
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.state.messages import LLMModel
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.elements.user_config import enable_pi_agent
from sculptor.testing.pages.settings_page import PlaywrightSettingsPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage

_ResponseT = TypeVar("_ResponseT")


def get_any_onboarding_step(page: Page) -> Locator:
    """Return a locator that matches any onboarding wizard step."""
    return (
        page.get_by_test_id(ElementIDs.ONBOARDING_WELCOME_STEP)
        .or_(page.get_by_test_id(ElementIDs.ONBOARDING_INSTALLATION_STEP))
        .or_(page.get_by_test_id(ElementIDs.ONBOARDING_ADD_REPO_STEP))
    )


def expect_app_not_onboarding(page: Page, app_element: Locator, *, timeout: int | None = None) -> None:
    """Wait for *app_element* to render, raising if the onboarding wizard shows instead.

    Waits for either *app_element* or any onboarding step to become visible,
    then raises ``RuntimeError`` if onboarding won.  Callers that need cleanup
    before the error propagates should wrap this in ``try / except``.
    """
    onboarding = get_any_onboarding_step(page)
    if timeout is not None:
        expect(app_element.or_(onboarding)).to_be_visible(timeout=timeout)
    else:
        expect(app_element.or_(onboarding)).to_be_visible()
    if not app_element.is_visible():
        raise RuntimeError(
            "OnboardingWizard is showing instead of the expected app element."
            + " Check that test user config, dependency stubs, and project registration are correct."
        )


def navigate_to_home_page(page: Page) -> None:
    """Navigate to the Home page (/home).

    Clicks the Home button in the top bar, or falls back to direct URL
    navigation when the button is not visible (e.g. on settings page).
    """
    home_button = page.get_by_test_id(ElementIDs.HOME_BUTTON)
    if home_button.is_visible():
        home_button.click()
        # Wait for the workspace list or empty state to appear
        workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
        empty_state = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_EMPTY_STATE)
        expect(workspace_rows.first.or_(empty_state)).to_be_visible(timeout=10000)
        return

    # Home button not visible — navigate via URL. Append the hash directly to
    # the base (no extra "/"): an injected slash would turn a document path
    # like ".../index.html" into ".../index.html/", breaking relative-to-
    # document asset resolution under the sculptor://app origin.
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto(f"{base_url}#/home")
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
    empty_state = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_EMPTY_STATE)
    expect(workspace_rows.first.or_(empty_state)).to_be_visible(timeout=10000)


def navigate_to_add_workspace_page(page: Page) -> None:
    """Navigate to the Add Workspace page (/ws/new).

    Clicks the "+" button in the workspace tabs bar, or is a no-op if the
    submit button is already visible (i.e. we're already on the page).
    Falls back to direct URL navigation when on a page that doesn't show
    workspace controls (e.g. settings).

    If an "Open Workspace" tab already exists in the tab bar, clicks it
    instead of creating a new one via "+".  This avoids creating duplicate
    tabs when the add-workspace page is still loading (e.g. fetching projects).
    """
    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    if submit_button.is_visible():
        return

    # If an add-workspace tab already exists (e.g. from an earlier redirect or
    # navigation), click it instead of creating a new one.  This handles the
    # case where we're already on /ws/new/<draftId> but the form is still
    # loading (showing a spinner while projects load).
    add_workspace_tab = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_TAB)
    if add_workspace_tab.count() > 0:
        add_workspace_tab.first.click()
        expect(submit_button).to_be_visible(timeout=45_000)
        return

    add_workspace_button = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON)
    if add_workspace_button.is_visible():
        add_workspace_button.click()
        expect(submit_button).to_be_visible(timeout=45_000)
        return

    # Neither button visible (e.g. on settings page) — navigate via URL.
    # Use the base URL without a hash to force the SPA to reinitialize from
    # the root loader, which redirects to /ws/new.  A hash-only goto can be
    # a no-op if the router thinks we're already on a /ws/new path.
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto(base_url)
    page.wait_for_load_state("domcontentloaded")
    expect(submit_button).to_be_visible(timeout=45_000)


def reset_active_panel_to_files(page: Page) -> None:
    """Click the files sidebar icon to ensure the file browser is active.

    Any test that clicks a different sidebar tab changes the
    ``activePanelPerZone`` atom.  Calling this resets it through normal
    UI interaction so subsequent tests start with the default panel visible.

    No-op if the sidebar icons aren't visible (e.g. on the Add Workspace page).
    """
    files_icon = page.get_by_test_id(ElementIDs.PANEL_ICON_FILES)
    if files_icon.is_visible():
        files_icon.click()
        # Click again to ensure the panel is *active* (first click might toggle
        # it closed if it was already active, second click re-opens it).
        if not page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL).is_visible():
            files_icon.click()


_MAX_WORKSPACE_DELETE_ITERATIONS = 50


def delete_all_workspaces_via_ui(page: Page) -> None:
    """Delete every workspace through the UI and land on the Add Workspace page.

    Phase 1: For each open workspace tab, right-click → Delete → Confirm.
    Phase 2: Navigate to the Add Workspace page, then delete any remaining
    workspace rows (closed-but-not-deleted workspaces) via their inline
    delete buttons.
    """
    # Dismiss any open popover/context menu that might intercept clicks.
    page.keyboard.press("Escape")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    confirm_button = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
    confirm_dialog = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    # Phase 1: Delete all open workspace tabs.
    for _ in range(_MAX_WORKSPACE_DELETE_ITERATIONS):
        if workspace_tabs.count() == 0:
            break
        workspace_tabs.first.click(button="right")
        delete_item = page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE).first
        expect(delete_item).to_be_visible()
        delete_item.click()
        expect(confirm_button).to_be_visible()
        confirm_button.click()
        expect(confirm_dialog).to_be_hidden()
    else:
        remaining = workspace_tabs.count()
        logger.error(
            "Failed to delete all workspace tabs after {} iterations ({} remaining)",
            _MAX_WORKSPACE_DELETE_ITERATIONS,
            remaining,
        )
        raise RuntimeError(
            f"Could not delete all workspace tabs after {_MAX_WORKSPACE_DELETE_ITERATIONS} iterations ({remaining} remaining)"
        )

    # Close any leftover pseudo-tabs (Settings, Component Gallery, Open Workspace)
    # that a previous test may have opened.  These persist in localStorage and
    # can interfere with navigation expectations in subsequent tests.
    for tab_test_id in (ElementIDs.SETTINGS_TAB, ElementIDs.COMPONENT_GALLERY_TAB):
        tab = page.get_by_test_id(tab_test_id)
        if tab.is_visible():
            tab.hover()
            close_btn = tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
            expect(close_btn).to_be_visible()
            close_btn.click()
            expect(tab).not_to_be_visible()

    # Close extra "Open Workspace" tabs (multiple can exist now).
    # Leave at most one — it won't have a close button when it's the sole tab.
    add_workspace_tabs = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_TAB)
    while add_workspace_tabs.count() > 1:
        tab = add_workspace_tabs.first
        tab.hover()
        close_btn = tab.get_by_test_id(ElementIDs.TAB_CLOSE_BUTTON)
        expect(close_btn).to_be_visible()
        close_btn.click()

    navigate_to_home_page(page)

    # Phase 2: Delete any remaining workspaces from the workspace list
    # on the home page (these were closed but not deleted by the test).
    # navigate_to_home_page already waits for workspace rows or empty state.
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)

    for _ in range(_MAX_WORKSPACE_DELETE_ITERATIONS):
        if workspace_rows.count() == 0:
            break
        delete_button = workspace_rows.first.get_by_test_id(ElementIDs.WORKSPACE_ROW_CONTEXT_MENU_DELETE)
        expect(delete_button).to_be_visible()
        delete_button.click()
        expect(confirm_button).to_be_visible()
        confirm_button.click()
        expect(confirm_dialog).to_be_hidden()
    else:
        remaining = workspace_rows.count()
        logger.error(
            "Failed to delete all workspace rows after {} iterations ({} remaining)",
            _MAX_WORKSPACE_DELETE_ITERATIONS,
            remaining,
        )
        raise RuntimeError(
            f"Could not delete all workspace rows after {_MAX_WORKSPACE_DELETE_ITERATIONS} iterations ({remaining} remaining)"
        )


_workspace_name_counter = itertools.count(1)


def start_task_and_wait_for_ready(
    sculptor_page: Page,
    prompt: str = "",
    wait_for_agent_to_finish: bool = True,
    model_name: str | None = FAKE_CLAUDE_MODEL_NAME,
    workspace_name: str | None = None,
    mode: str | None = None,
    agent_type: str | None = None,
) -> PlaywrightTaskPage:
    """Create a workspace and agent through the Add Workspace UI.

    Navigates to the Add Workspace form by clicking the "+" button in the
    workspace tabs bar, fills in the workspace name, clicks submit,
    then waits for the agent chat page to appear.  If the Add Workspace form
    is already showing (e.g. no workspaces exist yet), skips the "+" click.

    The Add Workspace page no longer has a model selector, so the model
    is switched on the chat panel once the workspace is ready.

    When *prompt* is provided, it is sent as the first chat message after the
    workspace is created (the Add Workspace page has no prompt input).

    When *prompt* is empty the agent is created in a waiting state and
    ``wait_for_agent_to_finish`` is ignored.

    Defaults to the Fake Claude model, which returns deterministic responses
    without LLM calls.  Tests that need a real agent should pass an explicit model name.
    Pass ``model_name=None`` to skip model selection entirely — useful for tests
    that only need the workspace UI shell and do not exercise the agent (e.g. in
    packaged-release runs where Fake Claude is gated off).

    By default the workspace is created in WORKTREE mode (the product default).
    Tests that exercise CLONE-specific semantics (e.g. ``origin/*`` remote
    refs in the workspace's checkout) can pass ``mode="CLONE"`` — the helper
    will enable the clone-workspaces flag, reload, then pick CLONE in the
    mode selector before submitting.
    """
    if mode == "CLONE":
        enable_clone_workspaces(sculptor_page)
    elif mode not in (None, "WORKTREE"):
        raise ValueError(f"unsupported mode: {mode!r}; expected None, 'WORKTREE', or 'CLONE'")

    if agent_type not in (None, "claude", "pi", "terminal"):
        raise ValueError(f"unsupported agent_type: {agent_type!r}; expected None, 'claude', 'pi', or 'terminal'")
    # Only the pi *option* is gated behind the experimental pi-agent flag
    # (the agent-type select itself is always visible) — enable the flag
    # before navigating so the option is present.
    if agent_type == "pi":
        enable_pi_agent(sculptor_page)

    navigate_to_add_workspace_page(sculptor_page)

    # Fill in the workspace name. Each call gets a unique name by default so
    # the auto-generated worktree branch (`<user>/<slug>`) doesn't collide
    # when a test creates multiple workspaces. Callers that need a specific
    # name can still pass one explicitly.
    if workspace_name is None:
        workspace_name = f"Test Workspace {next(_workspace_name_counter)}"
    workspace_name_input = sculptor_page.get_by_test_id(ElementIDs.WORKSPACE_NAME_INPUT)
    workspace_name_input.fill(workspace_name)

    if mode == "CLONE":
        sculptor_page.get_by_test_id(ElementIDs.MODE_SELECTOR).click()
        sculptor_page.get_by_test_id(ElementIDs.MODE_OPTION_CLONE).click()

    # When an agent type is requested, drive the first-agent type select
    # before submitting. Defaults to Claude (the form default) when omitted.
    if agent_type is not None:
        sculptor_page.get_by_test_id(ElementIDs.ADD_WORKSPACE_AGENT_TYPE_SELECT).click()
        option_id = {
            "claude": ElementIDs.AGENT_TYPE_OPTION_CLAUDE,
            "pi": ElementIDs.AGENT_TYPE_OPTION_PI,
            "terminal": ElementIDs.AGENT_TYPE_OPTION_TERMINAL,
        }[agent_type]
        sculptor_page.get_by_test_id(option_id).click()

    # Wait for the submit button to be enabled — repo info loaded, AND the
    # worktree-mode branch-name preview has populated the input (the page
    # gates submit on a non-empty branch name in worktree mode).
    submit_button = sculptor_page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_enabled()

    # Click create workspace
    submit_button.click()

    # A terminal first agent has no chat surface — wait for the terminal
    # panel instead and skip the chat-panel/model/prompt steps entirely.
    if agent_type == "terminal":
        terminal_panel_locator = sculptor_page.get_by_test_id(ElementIDs.AGENT_TERMINAL_PANEL)
        expect(terminal_panel_locator).to_be_visible(timeout=60_000)
        return PlaywrightTaskPage(page=sculptor_page)

    # Wait for the chat panel to appear (indicates we navigated to the agent page).
    # On contended CI runners the workspace clone + environment setup can take >30s.
    chat_panel_locator = sculptor_page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel_locator).to_be_visible(timeout=60_000)

    task_page = PlaywrightTaskPage(page=sculptor_page)
    chat_panel = task_page.get_chat_panel()

    # Switch the agent to the requested model on the chat panel, since the
    # Add Workspace form no longer offers a model selector.  The model-selector
    # click steals focus from the chat input, so restore it afterwards — tests
    # that assert post-creation focus rely on this.
    if model_name is not None:
        select_model_by_name(chat_panel=chat_panel, model_name=model_name)
        # The model selector is a Radix Select; closing it restores focus to its
        # trigger asynchronously (FocusScope onUnmountAutoFocus -> trigger.focus()).
        # Wait for that restore to land before focusing the chat input below, so the
        # late refocus can't steal focus back from it.
        expect(chat_panel.get_model_selector()).to_be_focused()
    chat_input = chat_panel.get_chat_input()
    chat_input.focus()

    if prompt:
        # Send the prompt as the first chat message
        type_into_tiptap(sculptor_page, chat_input, prompt)
        send_button = chat_panel.get_send_button()
        expect(send_button).to_be_enabled()
        send_button.click()
        # Wait for either terminal state: editor cleared (success) or send
        # button advertising `data-last-send-error` (failure). Racing them
        # lets a failed send fail loudly instead of timing out on the
        # empty-text assertion below.
        sculptor_page.wait_for_function(
            """({ inputTestId, btnTestId }) => {
              const btn = document.querySelector(`[data-testid="${btnTestId}"]`);
              if (btn && btn.hasAttribute('data-last-send-error')) return true;
              const input = document.querySelector(`[data-testid="${inputTestId}"]`);
              return !!input && (input.textContent ?? '').trim() === '';
            }""",
            arg={"inputTestId": ElementIDs.CHAT_INPUT, "btnTestId": ElementIDs.SEND_BUTTON},
            timeout=30_000,
        )
        send_error = send_button.get_attribute("data-last-send-error")
        if send_error is not None:
            raise AssertionError(f"send failed: {send_error}")
        expect(chat_input).to_have_text("")

        if wait_for_agent_to_finish:
            # Wait for the assistant's first reply to be attached (count >= 2).
            # This is a positive signal of agent activity that works in both
            # chat views and tolerates prompts that produce more than one
            # assistant message (e.g. auto_compact flows).  Without it, the
            # not_to_be_visible check below can pass trivially during the gap
            # between send-click and the activity indicator rendering.
            expect(chat_panel.get_messages().nth(1), "agent reply to appear").to_be_attached()
            expect(chat_panel.get_thinking_indicator(), "to finish outputting data").not_to_be_visible()

    return task_page


def add_agent_and_wait_for_ready(page: Page) -> PlaywrightTaskPage:
    """Click the agent tab "+" to add an agent and wait until the new agent is
    the active one, with a chat input ready to receive a message.

    Returns a ``PlaywrightTaskPage`` bound to the new (now-active) agent.

    Adding an agent navigates to it only after an async create request
    resolves, but the agent-tab count flips to N+1 as soon as the agent-list
    query refreshes — which can happen before that navigation lands.  Callers
    must not type into the chat input until the switch completes, or the text
    lands in the outgoing agent's editor (or no editor, mid-remount).  Waiting
    for the URL to point at a different agent id is the settle signal.
    """
    task_page = PlaywrightTaskPage(page=page)
    previous_agent_id = task_page.get_task_id()
    agent_tab_bar = task_page.get_agent_tab_bar()
    existing_tab_count = agent_tab_bar.get_agent_tabs().count()

    agent_tab_bar.get_add_agent_button().click()
    expect(agent_tab_bar.get_agent_tabs()).to_have_count(existing_tab_count + 1)

    # The create-agent POST and clone/setup can be slow on contended runners.
    page.wait_for_function(
        r"""(previousAgentId) => {
            const match = window.location.href.match(/\/agent\/([A-Za-z0-9_-]+)/);
            return match !== null && match[1] !== previousAgentId;
        }""",
        arg=previous_agent_id,
        timeout=60_000,
    )

    new_task_page = PlaywrightTaskPage(page=page)
    # The chat input is keyed by agent id, so it remounts for the new agent;
    # wait for it to attach before callers type into it.
    expect(new_task_page.get_chat_panel().get_chat_input()).to_be_visible()
    return new_task_page


def navigate_to_frontend(page: Page, url: str, retry_seconds: float = 60) -> Page:
    """Navigate the browser to the Sculptor frontend URL with retries.

    Returns the raw Page rather than a page-object wrapper so callers can
    wrap it in whatever page object is appropriate for their context.
    """
    base_url = url

    retry_goto = retry(
        stop=stop_after_delay(retry_seconds),
        wait=wait_fixed(1),
        retry=retry_if_exception_type(playwright.sync_api.Error),
        reraise=True,
    )(lambda: page.goto(base_url))

    try:
        retry_goto()
    except RetryError as e:
        log_exception(
            e,
            "Failed to load page at {base_url} after {retry_seconds}s",
            base_url=base_url,
            retry_seconds=retry_seconds,
        )
        raise

    return page


# Substrings of a Playwright APIRequestContext error message that mean the
# request never reached a server-side handler — see request_with_retry.
_TRANSIENT_CONNECTION_ERROR_MARKERS = ("socket hang up", "econnreset")


def _is_transient_connection_error(exception: BaseException) -> bool:
    """Return True for a Playwright API error caused by a dropped keep-alive connection.

    ``page.request`` keeps an HTTP keep-alive connection pool alive for the
    lifetime of the shared test ``page``.  When the Sculptor server closes an
    idle pooled connection on its keep-alive timeout, the next request that
    reuses that socket fails with ``socket hang up`` / ``ECONNRESET`` *before*
    the server reads it, so no HTTP response is produced.
    """
    if not isinstance(exception, playwright.sync_api.Error):
        return False
    message = exception.message.lower()
    return any(marker in message for marker in _TRANSIENT_CONNECTION_ERROR_MARKERS)


def request_with_retry(
    request_method: Callable[..., _ResponseT],
    url: str,
    *,
    retry_seconds: float = 30,
    **kwargs: object,
) -> _ResponseT:
    """Call a ``page.request.<verb>`` method, retrying dropped keep-alive connections.

    Retries only the connection drops classified by
    :func:`_is_transient_connection_error`, and only on the raised-exception
    path — when Playwright produced no response at all.  A retry therefore
    fires only when the first attempt provably had no server-side effect, so it
    cannot double-apply the request; any response, including a 4xx/5xx, is
    returned to the caller unretried.

    Mirrors the retry that :func:`navigate_to_frontend` applies to ``page.goto``.
    """
    retrying = retry(
        stop=stop_after_delay(retry_seconds),
        # A dropped pooled connection is recovered by reconnecting, not by
        # waiting — this spacing only avoids a tight loop on repeated drops.
        wait=wait_fixed(0.1),
        retry=retry_if_exception(_is_transient_connection_error),
        reraise=True,
    )(lambda: request_method(url, **kwargs))
    return retrying()


def navigate_to_settings_page(page: Page, **_kwargs: object) -> PlaywrightSettingsPage:
    """Open Settings the way a user does — click the gear in the top bar.

    The settings button lives in the persistent ``TopBar``, which ``PageLayout``
    renders on every in-app route (Home, Add Workspace, Workspace, Settings), so
    it is reachable from any state this helper is called from — including the
    add-workspace page that pre-test cleanup lands on after deleting all
    workspaces. Clicking routes via React Router with no document reload, so it
    keeps the WebSocket connection alive and avoids re-fetching ``index.html``
    (and its assets) under the ``sculptor://app`` origin, where the built
    renderer references assets via absolute paths.

    The click is retried until the settings page actually renders. A single
    click can lose a race with an in-flight imperative redirect: deleting the
    last workspace makes WorkspacePage queue a ``navigate("/ws/new/<uuid>")``
    that may commit *after* our navigation and bounce us off ``/settings``.
    Re-clicking from the now-settled state lands cleanly — the redirect only
    fires while WorkspacePage is mounted, so once we reach Settings nothing
    redirects away again.
    """
    settings_button = page.get_by_test_id(ElementIDs.SETTINGS_BUTTON)
    settings_page_marker = page.get_by_test_id(ElementIDs.SETTINGS_PAGE)

    def _click_into_settings() -> None:
        expect(settings_button).to_be_visible(timeout=5_000)
        settings_button.click()
        expect(settings_page_marker).to_be_visible(timeout=5_000)

    retry(
        stop=stop_after_delay(30),
        wait=wait_fixed(0.1),
        retry=retry_if_exception_type(AssertionError),
        reraise=True,
    )(_click_into_settings)()
    return PlaywrightSettingsPage(page=page)


def delete_project_via_settings(
    page: Page, project_name: str, path_contains: str | None = None, **_kwargs: object
) -> None:
    """Delete a project through the Settings > Repositories UI.

    Navigates to the settings page, clicks Repositories, removes the named
    project, waits for the success toast, then navigates back home.
    """
    settings_page = navigate_to_settings_page(page=page)
    repos_section = settings_page.click_on_repositories()
    repos_section.remove_repo(project_name, path_contains=path_contains)

    # Navigate back to the Add Workspace page after deletion
    navigate_to_add_workspace_page(page)


def upload_file_via_api(page: Page, *, name: str, mime_type: str, content: bytes) -> str:
    """Upload a file through the harness-agnostic upload endpoint, returning its id.

    The endpoint accepts any file type — the image-only validation lives in the
    frontend — so this is how an integration test attaches a non-image file the
    UI would refuse. ``page.request`` inherits the page's session cookie.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    response = page.request.post(
        f"{base_url}/api/v1/upload-file",
        multipart={"file": {"name": name, "mimeType": mime_type, "buffer": content}},
    )
    assert response.ok, f"upload-file failed: {response.status} {response.text()}"
    # The endpoint serializes UploadFileResponse with a camelCase alias, so the
    # JSON key is `fileId` (matching the frontend's FileUploadUtils reader).
    return response.json()["fileId"]


def send_message_via_api(
    page: Page, *, message: str, files: Sequence[str], model: LLMModel = LLMModel.CLAUDE_4_OPUS_200K
) -> None:
    """Send a chat message (with attached upload ids) to the active agent via the API.

    Parses the workspace/agent ids from the page URL (``/ws/<ws>/agent/<agent>``).
    pi ignores ``model`` (it reads its own ``models.json``), so the default is
    only a schema-valid placeholder for pi workspaces.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    match = re.search(r"/ws/([^/]+)/agent/([^/?#]+)", page.url)
    assert match is not None, f"could not parse workspace/agent ids from URL: {page.url}"
    workspace_id, agent_id = match.group(1), match.group(2)
    response = page.request.post(
        f"{base_url}/api/v1/workspaces/{workspace_id}/agents/{agent_id}/messages",
        data={"message": message, "model": model.value, "files": files},
    )
    assert response.ok, f"send-message failed: {response.status} {response.text()}"


# NOTE: The helpers below use page.goto() and page.evaluate(), which are
# exceptions to our rules against those APIs in integration tests.  Each
# docstring explains why the escape hatch is necessary.  By centralizing them
# here, the test files themselves stay free of raw goto/evaluate calls.


def soft_reload_page(page: Page, wait_until: str | None = None) -> None:
    """Re-navigate to the current URL to refresh frontend state.

    This is used instead of ``page.reload()`` which causes
    ``ERR_INSUFFICIENT_RESOURCES`` on CI runners because Chromium cannot
    re-fetch all unbundled Vite dev server modules while the old page still
    holds resources.  Navigating to the same URL achieves a fresh navigation
    without the resource contention.
    """
    if wait_until is not None:
        page.goto(page.url, wait_until=wait_until)
    else:
        page.goto(page.url)


def navigate_away_and_back(page: Page) -> None:
    """Navigate to the Add Workspace page and back to force Jotai store reinitialization.

    The Sculptor frontend caches state in Jotai atoms that are initialized from
    localStorage on first load.  A hash-only navigation within the SPA does not
    unload/reload atoms.  By navigating to a different route (``#/ws/new``) and
    then back, we force the atoms to reinitialize from whatever values are
    currently in localStorage.
    """
    current_url = page.url
    base_url = current_url.split("#")[0].rstrip("/")
    page.goto(f"{base_url}#/ws/new")
    expect(page.get_by_test_id(ElementIDs.START_TASK_BUTTON)).to_be_visible()
    page.goto(current_url)


def full_spa_reload(page: Page, target_hash: str = "#/") -> None:
    """Force a full SPA unload/reload by navigating through ``about:blank``.

    Hash-only navigation (e.g. from ``/#/ws/1`` to ``/#/``) does not unload
    the SPA, so cached Jotai atoms and in-memory state persist.  Going through
    ``about:blank`` first forces the browser to fully tear down and re-create
    the page, clearing all in-memory state.

    ``target_hash`` is appended directly to the base URL, so it must start with
    ``#`` (not ``/#``): an injected slash would turn a document path like
    ``.../index.html`` into ``.../index.html/`` and break relative-to-document
    asset resolution under the sculptor://app origin.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto("about:blank")
    page.goto(f"{base_url}{target_hash}")
    # NOTE: Do NOT use page.wait_for_load_state("networkidle") here — the
    # frontend maintains a persistent WebSocket connection that prevents
    # networkidle from ever being reached, causing an indefinite hang.
    page.wait_for_load_state("domcontentloaded")


def set_local_storage_items(page: Page, items: Mapping[str, str]) -> None:
    """Set multiple localStorage key-value pairs in the browser.

    Used to simulate pre-existing user state (e.g. panel layouts saved by a
    previous version of Sculptor) before navigating to test that the frontend
    handles stale or incomplete localStorage gracefully.
    """
    js_lines = [f"localStorage.setItem({json.dumps(k)}, {json.dumps(v)});" for k, v in items.items()]
    js_body = "\n        ".join(js_lines)
    page.evaluate(f"""() => {{
        {js_body}
    }}""")


def get_local_storage_item(page: Page, key: str) -> str | None:
    """Read a single value from localStorage and JSON-parse it.

    Returns the parsed value, or ``None`` if the key does not exist.
    This is the read counterpart to ``set_local_storage_items``.
    """
    return page.evaluate(
        """(key) => {
            const raw = localStorage.getItem(key);
            return raw === null ? null : JSON.parse(raw);
        }""",
        key,
    )


def remove_local_storage_item(page: Page, key: str) -> None:
    """Remove a single key from localStorage.

    Used to simulate pre-upgrade state where a localStorage key does not
    yet exist, forcing the frontend to fall through to a migration or
    default-initialization path.
    """
    page.evaluate("(key) => localStorage.removeItem(key)", key)


def blur_page(page: Page) -> None:
    """Click the page body at the origin to remove focus from all inputs.

    This is used in tests that need to verify focus behavior: first blur
    everything, then trigger the action that should set focus.

    NOTE: This uses ``page.locator("body")`` which is an exception to our rule
    against CSS selectors in integration tests.  There is no ``data-testid`` on
    ``<body>`` and adding one would be unusual; the ``body`` selector is stable
    and unlikely to break.
    """
    page.locator("body").click(position={"x": 0, "y": 0})


def blur_active_element(page: Page) -> None:
    """Remove focus from whichever element currently has it.

    Useful before pressing keyboard shortcuts: if focus is trapped in a text
    input (e.g. the chat input or workspace name field) the keypress may be
    consumed by the input instead of bubbling to the app-level shortcut handler.
    """
    page.evaluate("document.activeElement?.blur()")


def navigate_to_workspace_without_agent(page: Page, workspace_id: str) -> None:
    """Navigate to a workspace URL without an agent ID, keeping the WebSocket alive.

    ``page.goto()`` triggers a full SPA reload even for hash-only URL changes,
    which disconnects the WebSocket and resets ``isSingletonWebsocketActiveAtom``
    to ``false``.  When the atom is false, ``getWorkspaceMruAgent()`` uses a
    no-op tracker and returns immediately — masking the bug where the call
    blocks for ~10 seconds waiting for a WS acknowledgment.

    Assigning ``window.location.hash`` directly fires a ``hashchange`` event
    without any page reload, so the WebSocket stays connected.  This is the
    correct way to simulate a user clicking a workspace tab (which also does
    a hash-only navigation via React Router).
    """
    page.evaluate(f"window.location.hash = '/ws/{workspace_id}'")


def get_electron_app_version(page: Page) -> str:
    """Return the Electron ``app.getVersion()`` string from the running instance.

    ``electron-updater`` compares the manifest version against this value to
    decide whether an update is available.  In dev mode it returns ``"0.0.0"``
    (from ``package.json``); in packaged builds it returns the real semver set
    during packaging.
    """
    version: str = page.evaluate("window.sculptor.getAppVersion()")
    return version
