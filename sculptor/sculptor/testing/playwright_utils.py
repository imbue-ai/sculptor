from __future__ import annotations

import itertools
import json
from collections.abc import Callable
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

from imbue_core.async_monkey_patches import log_exception
from sculptor.constants import ElementIDs
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.elements.user_config import enable_multi_harness
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


def get_app_ready_beacon(page: Page) -> Locator:
    """Locator that resolves once the SPA shell has finished its initial render.

    The beacon is the topbar "+" (``ADD_WORKSPACE_BUTTON``) OR the inline
    new-workspace form's submit button (``START_TASK_BUTTON``): the "+" is
    hidden on an empty Home, where the inline form is the create surface, so
    either one means the app rendered. The two are mutually exclusive on
    /home, so the union never matches two elements — do NOT append ``.first``
    when handing this to ``expect_app_not_onboarding``, which composes its own
    ``.or_(onboarding)`` that a trailing ``.first`` would break.
    """
    return page.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON).or_(page.get_by_test_id(ElementIDs.START_TASK_BUTTON))


def navigate_to_home_page(page: Page) -> None:
    """Navigate to the Home page (/home).

    Clicks the Home button when on a non-home route, or reloads when
    already on /home so the workspace list refetches. ``RecentWorkspaces``
    only fetches once on mount, so a no-op home click after CLI/external
    workspace changes would leave the list stale.
    """
    home_button = page.get_by_test_id(ElementIDs.HOME_BUTTON)
    is_on_home = "#/home" in page.url

    if is_on_home:
        # Force HomePage / RecentWorkspaces to remount and refetch via a
        # full SPA reload — useHomeToggle treats Home button on /home as a
        # no-op when there are no visible tabs to bounce to, and a soft
        # ``page.goto(page.url)`` to a hash-only URL doesn't tear down the
        # SPA, so RecentWorkspaces wouldn't pick up CLI-created workspaces.
        # ``page.reload()`` is avoided because it triggers
        # ERR_INSUFFICIENT_RESOURCES on CI runners.
        full_spa_reload(page, target_hash="/#/home")
    elif home_button.is_visible():
        home_button.click()
    else:
        base_url = page.url.split("#")[0].rstrip("/")
        page.goto(f"{base_url}/#/home")

    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
    inline_new_workspace_form = page.get_by_test_id(ElementIDs.HOME_NEW_WORKSPACE_FORM)
    expect(workspace_rows.first.or_(inline_new_workspace_form)).to_be_visible(timeout=10000)


def open_new_workspace_modal(page: Page) -> None:
    """Ensure the new-workspace form is visible with its inputs ready.

    No-op when the submit button is already visible — either the modal is
    open, or (on an empty Home) the inline form is already rendered.
    Otherwise clicks the topbar "+" to open the modal.

    The "+" is intentionally hidden on an empty Home (the inline form is the
    create surface there), so we wait for *either* the create form or the
    "+" and only click the "+" when the form isn't already showing.
    """
    submit_button = page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    add_workspace_button = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_BUTTON)

    # Wait for either the create form (inline on an empty Home, or an
    # already-open modal) or the topbar "+".  The early ``is_visible()`` check
    # below doesn't wait, so on a freshly-spawned instance the SPA may still be
    # on the loading spinner — polling on the union avoids racing the mount.
    # ``.first`` keeps the assertion single-element (Playwright strict mode) for
    # the brief windows where both a topbar "+" and a form submit button can be
    # in the DOM at once (e.g. the "+" plus an open modal).
    expect(submit_button.or_(add_workspace_button).first).to_be_visible(timeout=45_000)
    if submit_button.is_visible():
        return
    add_workspace_button.click()
    expect(submit_button).to_be_visible(timeout=45_000)


def reset_active_panel_to_files(page: Page) -> None:
    """Click the files sidebar icon to ensure the file browser is active.

    Any test that clicks a different sidebar tab changes the
    ``activePanelPerZone`` atom.  Calling this resets it through normal
    UI interaction so subsequent tests start with the default panel visible.

    No-op if the sidebar icons aren't visible (e.g. when the new-workspace
    modal is open or we're on the Home page).
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
    """Delete every workspace through the UI and land on the Home page.

    Phase 1: For each open workspace tab, right-click → Delete → Confirm.
    Phase 2: Navigate to the Home page, then delete any remaining workspace
    rows (closed-but-not-deleted workspaces) via their inline delete buttons.
    """
    # Dismiss any open popover/context menu that might intercept clicks.
    page.keyboard.press("Escape")

    workspace_tabs = page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
    confirm_button = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
    confirm_dialog = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    # Phase 1: Delete all open workspace tabs.
    for i in range(_MAX_WORKSPACE_DELETE_ITERATIONS):
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

    navigate_to_home_page(page)

    # Phase 2: Delete any remaining workspaces from the workspace list
    # on the home page (these were closed but not deleted by the test).
    # navigate_to_home_page already waits for workspace rows or empty state.
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)

    for i in range(_MAX_WORKSPACE_DELETE_ITERATIONS):
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
    harness: HarnessName | None = None,
) -> PlaywrightTaskPage:
    """Create a workspace and agent through the new-workspace modal.

    Opens the new-workspace form — the topbar "+" modal, or the inline form
    shown on an empty Home when no workspaces exist yet — fills in the
    workspace name, clicks submit, then waits for the agent chat page to
    appear.

    The modal does not expose a model selector, so the model is switched
    on the chat panel once the workspace is ready.

    When *prompt* is provided, it is sent as the first chat message after
    creation. We deliberately don't use the modal's prompt textarea here:
    callers expect ``select_model_by_name`` to apply, and chat-panel
    sending is the only path that runs through the model-switch helper.

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

    # The harness picker is gated behind the experimental multi-harness flag
    # (off by default). Any explicit harness selection drives the picker below,
    # so enable the flag before navigating so the picker is present.
    if harness is not None:
        enable_multi_harness(sculptor_page)

    open_new_workspace_modal(sculptor_page)

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

    # When a harness is requested, drive the picker before submitting so the
    # selection is persisted on the workspace row. Defaults to Claude (the form
    # default) when omitted.
    if harness is not None:
        sculptor_page.get_by_test_id(ElementIDs.HARNESS_SELECTOR).click()
        option_id = ElementIDs.HARNESS_OPTION_PI if harness == HarnessName.PI else ElementIDs.HARNESS_OPTION_CLAUDE
        sculptor_page.get_by_test_id(option_id).click()

    # Wait for the submit button to be enabled — repo info loaded, AND the
    # worktree-mode branch-name preview has populated the input (the page
    # gates submit on a non-empty branch name in worktree mode).
    submit_button = sculptor_page.get_by_test_id(ElementIDs.START_TASK_BUTTON)
    expect(submit_button).to_be_enabled()

    # Click create workspace
    submit_button.click()

    # Wait for the chat panel to appear (indicates we navigated to the agent page).
    # On Fly runners the workspace clone + environment setup can take >30s.
    chat_panel_locator = sculptor_page.get_by_test_id(ElementIDs.CHAT_PANEL)
    expect(chat_panel_locator).to_be_visible(timeout=60_000)

    task_page = PlaywrightTaskPage(page=sculptor_page)
    chat_panel = task_page.get_chat_panel()

    # Switch the agent to the requested model on the chat panel, since the
    # new-workspace modal does not offer a model selector. The model-selector
    # click steals focus from the chat input, so restore it afterwards —
    # tests that assert post-creation focus rely on this.
    if model_name is not None:
        select_model_by_name(chat_panel=chat_panel, model_name=model_name)
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
    """Navigate to the settings page via direct URL."""
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto(f"{base_url}/#/settings")
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

    # Re-open the new-workspace modal so callers see the same post-deletion
    # state they got before the modal migration.
    open_new_workspace_modal(page)


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


def trigger_root_loader(page: Page) -> None:
    """Navigate to the bare URL so the SPA's rootLoader fires.

    ``spawn_instance`` lands directly on ``/#/home`` to skip the rootLoader.
    Restart-style tests that want to exercise the loader's MRU / no-MRU
    routing logic (the actual subject under test) can call this helper to
    navigate through ``/`` and let the loader take them where it would.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto(base_url)


def navigate_away_and_back(page: Page) -> None:
    """Hash-navigate to /home and back to force component remount.

    The state-restoration tests that use this helper (pending Q&A panels,
    plan-mode revisions, etc.) want to verify that the workspace page
    rebuilds the in-progress UI from atoms when the user clicks away and
    comes back. They rely on Jotai's *in-memory* atom values — about:blank
    or a real reload would wipe them and the test would assert against an
    empty page instead. Hash-only navigation re-mounts the route's
    component tree without unloading the SPA, which is the right grain:
    components remount, atoms persist.

    The pre-modal helper went to ``#/ws/new``; that route is gone, so
    ``#/home`` is the modal-flow equivalent — it triggers a full
    workspace-page unmount without reloading atoms.
    """
    current_url = page.url
    base_url = current_url.split("#")[0].rstrip("/")
    page.goto(f"{base_url}/#/home")
    # Confirm Home rendered before going back.
    expect(get_app_ready_beacon(page)).to_be_visible()
    page.goto(current_url)


def full_spa_reload(page: Page, target_hash: str = "/#/home") -> None:
    """Force a full SPA unload/reload by navigating through ``about:blank``.

    Hash-only navigation (e.g. from ``/#/ws/1`` to ``/#/``) does not unload
    the SPA, so cached Jotai atoms and in-memory state persist.  Going through
    ``about:blank`` first forces the browser to fully tear down and re-create
    the page, clearing all in-memory state.

    The default ``target_hash`` lands on ``/home`` directly (skipping the
    ``/`` rootLoader's MRU redirect) so the reload deterministically returns
    to Home and re-runs its once-on-mount recent-workspaces fetch. Callers
    that want a specific route (a workspace URL, settings, etc.) should pass
    it explicitly.
    """
    base_url = page.url.split("#")[0].rstrip("/")
    page.goto("about:blank")
    page.goto(f"{base_url}{target_hash}")
    # NOTE: Do NOT use page.wait_for_load_state("networkidle") here — the
    # frontend maintains a persistent WebSocket connection that prevents
    # networkidle from ever being reached, causing an indefinite hang.
    page.wait_for_load_state("domcontentloaded")


def set_local_storage_items(page: Page, items: dict[str, str]) -> None:
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
