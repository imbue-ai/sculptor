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
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.user_config import enable_clone_workspaces
from sculptor.testing.elements.user_config import enable_pi_agent
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.pages.settings_page import PlaywrightSettingsPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.utils import get_playwright_modifier_key

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


def _expect_home_landed(page: Page) -> None:
    """Wait for the Home destination to render after navigating to ``/home``.

    The ``/home`` route resolves to one of two pages depending on the workspace
    list. With workspaces it is the Home list page, which shows workspace rows
    (or, in the search-empty case, the ``ADD_WORKSPACE_EMPTY_STATE`` heading).
    With NO workspaces the app gate swaps in the empty-first-run page instead —
    it renders neither of those, just the inline new-workspace form keyed by
    ``EMPTY_FIRST_RUN_PAGE``. All three are valid "we landed on Home" signals;
    waiting on only the first two times out whenever the list is empty (e.g.
    right after pre-test cleanup deletes every workspace).
    """
    workspace_rows = page.get_by_test_id(ElementIDs.WORKSPACE_ROW)
    empty_state = page.get_by_test_id(ElementIDs.ADD_WORKSPACE_EMPTY_STATE)
    empty_first_run = page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE)
    expect(workspace_rows.first.or_(empty_state).or_(empty_first_run)).to_be_visible(timeout=10000)


def ensure_sidebar_expanded(page: Page) -> None:
    """Expand the sidebar when a prior step collapsed it.

    Collapsing does not hide the sidebar — it unmounts it (``AppShell`` and the
    empty first-run page render ``CollapsedSidebarToggle`` in its place), so
    while collapsed the sidebar's nav links do not exist in the DOM at all.
    Helpers that click sidebar chrome call this first so they find their
    targets even after a collapse — whether by the test itself or leftover from
    the previous test on the shared instance (per-test cleanup runs against the
    prior test's end state before the browser reset restores the default).

    Waits for one of the two mutually exclusive shell states (rail or expand
    icon) to render before deciding, so a call racing a fresh page load doesn't
    misread "not rendered yet" as "expanded". The only surface rendering
    neither is the onboarding wizard, where sidebar navigation is meaningless —
    a timeout here is the correct loud failure.
    """
    sidebar = page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    expand_icon = page.get_by_test_id(ElementIDs.SIDEBAR_EXPAND_ICON)
    expect(sidebar.or_(expand_icon)).to_be_visible()
    if expand_icon.is_visible():
        expand_icon.click()
    expect(sidebar).to_be_visible()


def navigate_to_home_page(page: Page) -> None:
    """Navigate to the Home page (/home) via the sidebar Home link.

    The sidebar renders on every in-app route (``AppShell`` hosts them all, and
    the empty first-run page mounts its own copy), so the Home link is always
    reachable once the sidebar is expanded — ``ensure_sidebar_expanded``
    restores it when a prior step collapsed the rail.
    """
    ensure_sidebar_expanded(page)
    sidebar_home_link = page.get_by_test_id(ElementIDs.SIDEBAR_HOME_LINK)
    expect(sidebar_home_link).to_be_visible()
    sidebar_home_link.click()
    _expect_home_landed(page)


def navigate_to_workspace(page: Page, name_or_index: str | int = 0) -> None:
    """Navigate to a workspace by clicking its sidebar row.

    Navigation happens through the sidebar's workspace rows (the successor to
    the home-page rows). ``name_or_index`` selects the row by its visible name
    (substring match) or by zero-based position.

    Workspace rows only exist while at least one workspace does, so callers
    must have created (or be positioned on) a workspace already.
    """
    # The new-workspace modal renders a dimmed dialog overlay that covers the
    # whole page, so a sidebar row beneath it is not clickable (Playwright's
    # actionability check fails on "stable"). A common caller sequence is
    # ``open_new_workspace_form`` (which opens that modal) then
    # ``navigate_to_workspace`` to return — so dismiss the modal first.
    # (First, before expanding the sidebar: the overlay would intercept the
    # expand-toggle click too.)
    dialog = page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)
    if dialog.count() > 0:
        page.keyboard.press("Escape")
        expect(dialog).to_have_count(0)

    ensure_sidebar_expanded(page)
    rows = page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)
    if isinstance(name_or_index, int):
        row = rows.nth(name_or_index)
    else:
        row = rows.filter(has_text=name_or_index)
    expect(row).to_be_visible()
    # Capture the target workspace id BEFORE clicking — the row button stamps it
    # as ``data-workspace-id`` — for the settle gate below. Reading it from the
    # row is race-free; the post-click URL is only a fallback because Playwright's
    # cached ``page.url`` can momentarily lag a hash-only navigation.
    target_workspace_id = row.get_attribute("data-workspace-id")
    row.click()
    # Settle on the workspace shell before returning so a caller that follows
    # with a non-retrying check doesn't race the route change. The landing signal
    # must hold in BOTH shell modes: the normal grid mounts SECTION_CENTER, but a
    # workspace restored to its per-workspace maximize renders ONLY the maximized
    # section's PanelSection (no SECTION_CENTER container), so keying on
    # SECTION_CENTER alone would time out there. Every rendered PanelSection —
    # normal or maximized, even a zero-agent workspace's empty center — carries
    # the sub-section-suffixed ring-host testid, so any match means the shell
    # landed. The testid is suffixed per sub-section (no single id to match), so
    # this uses a data-testid prefix selector, encapsulated here like the POMs'
    # tab selectors to honour the integration-test css-locator ratchet.
    #
    # Waiting on the ring host is race-free even though the ACTIVE-SECTION RING is
    # transient (it pulses on workspace entry and fades shortly after). The testid
    # names the PanelSection ROOT div, which stays mounted for as long as the
    # section renders; the ring itself is only a CSS ``::after`` overlay on that div
    # whose opacity fades via the ring-visible flag (RING_VISIBLE_MS). So the fade
    # never unmounts the element this waits on — only its overlay styling changes —
    # and the host cannot disappear out from under the wait.
    ring_hosts = page.locator(f'[data-testid^="{ElementIDs.SECTION_ACTIVE_RING}-"]')
    expect(ring_hosts.first).to_be_visible()
    # A visible ring-host is necessary but NOT sufficient: on a workspace→workspace
    # switch the route changes a commit before the layout scope flips (the flip lands
    # in useWorkspaceShellBootstrap's layout effect), so the PREVIOUS workspace's
    # ring-host is still mounted and this check can pass inside that pre-flip window —
    # a follow-up non-retrying POM snapshot would then read the old workspace's panels.
    # Gate on the shell's settle attribute, which WorkspaceLayoutShell stamps from
    # the post-flip scope (activeWorkspaceIdAtom), so it equals the target id only
    # once the layout atoms describe the new workspace. The workspace URL segment
    # (``/ws/<id>``, with or without an ``/agent/<id>`` suffix) backs up the row
    # attribute. Non-workspace destinations never reach here (this helper only
    # clicks workspace rows), so Home/Settings navigations are unaffected.
    if target_workspace_id is None:
        workspace_match = re.search(r"/ws/([^/?#]+)", page.url)
        target_workspace_id = workspace_match.group(1) if workspace_match is not None else None
    if target_workspace_id is not None:
        # data-active-workspace-id is a plain data attribute (its value is the id, not
        # a fixed testid), so it is matched by a raw attribute selector, encapsulated
        # here like the ring-host prefix selector above to honour the css-locator ratchet.
        settled_shell = page.locator("[data-active-workspace-id]")
        expect(settled_shell).to_have_attribute("data-active-workspace-id", target_workspace_id)


def get_workspace_creation_button(page: Page) -> tuple[Locator, bool]:
    """Resolve the workspace-creation surface and its create button.

    Two surfaces create a workspace, and both use ``NEW_WORKSPACE_CREATE_BUTTON``:
    the new-workspace modal (when workspaces already exist) and the inline
    empty-first-run form (when none do). They are distinguished by the modal's
    ``NEW_WORKSPACE_DIALOG`` wrapper, which only the modal renders.

    Waits for the create button to mount, then returns ``(button, is_inline_form)``
    where ``is_inline_form`` is true for the empty-first-run form (which pre-seeds
    the prompt) and false for the modal.
    """
    create_button = page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)
    expect(create_button).to_be_visible(timeout=45_000)
    is_inline_form = page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG).count() == 0
    return create_button, is_inline_form


def open_new_workspace_modal(page: Page) -> None:
    """Press the new-workspace keybinding until the modal's create button appears.

    The ``new_workspace`` shortcut (Cmd/Meta+T) is a ``window`` keydown handler,
    but a single press can be lost: focus may sit in the chat input (a prior
    ``start_task_and_wait_for_ready`` leaves it focused) or in a still-open / just-
    closed Radix overlay (a model/select dropdown), and while a dismissible overlay
    is the active element the shortcut hook's overlay-suppression branch swallows
    the press without opening the modal. Dismiss an intercepting overlay (Escape)
    and blur the active element before each press so it reaches the handler, then
    retry — a retried press is harmless because the modal toggle is keyed off the
    create button being absent (it is only pressed again while no modal is open).
    """
    create_button = page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)
    mod = get_playwright_modifier_key()

    def _press_and_wait() -> None:
        page.keyboard.press("Escape")
        blur_active_element(page)
        page.keyboard.press(f"{mod}+t")
        page.keyboard.up(mod)
        expect(create_button).to_be_visible(timeout=5_000)

    retry(
        stop=stop_after_delay(45),
        wait=wait_fixed(0.1),
        retry=retry_if_exception_type(AssertionError),
        reraise=True,
    )(_press_and_wait)()


def open_new_workspace_form(page: Page) -> None:
    """Bring up a workspace-creation surface (the new-workspace modal or inline form).

    No-op if a create surface is already showing — either the inline empty-first-run
    form or an already-open modal exposes ``NEW_WORKSPACE_CREATE_BUTTON``. Otherwise
    opens the new-workspace modal via the ``new_workspace`` keybinding (Cmd/Meta+T)
    and waits for its create button to appear.

    Callers may arrive parked on a surface that exposes NEITHER create button nor
    chat panel: the Settings page (a prior step navigated there, or a config flag
    helper's GET+PUT+``page.reload()`` reloaded the current ``/settings`` URL), or
    the Home workspace list (a prior step routed Home, and workspaces now exist so
    it renders the list rather than the empty-first-run inline form). Both are
    recognized below so the settle never times out, and from either the modal
    shortcut opens the create button.
    """
    create_button = page.get_by_test_id(ElementIDs.NEW_WORKSPACE_CREATE_BUTTON)
    # The center section is the "we are on a workspace" signal — present whatever the
    # active panel is. CHAT_PANEL alone misses a workspace whose active agent is a
    # terminal (no chat panel), which would leave the settle below with nothing to match.
    workspace_shell = page.get_by_test_id(ElementIDs.SECTION_CENTER)
    chat_panel = page.get_by_test_id(ElementIDs.CHAT_PANEL)
    settings_page = page.get_by_test_id(ElementIDs.SETTINGS_PAGE)
    # The empty-first-run page (no workspaces anywhere) hosts the inline create form,
    # but its create button only mounts AFTER the form finishes loading projects, so
    # the page can be parked here with no create button yet. This is its own settle
    # signal — and a multi-repo create-in-sequence routinely lands here between
    # workspaces (a create-and-delete leaves zero workspaces) — so it must be in the
    # settle set or a caller parked here times out before the button mounts.
    empty_first_run = page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE)
    # The Home workspace list (rows, or its search-empty heading) is a valid
    # parked surface too: it exposes no create button until the modal opens, so
    # it must be in the settle set or a caller parked there times out.
    home_list = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).first.or_(
        page.get_by_test_id(ElementIDs.ADD_WORKSPACE_EMPTY_STATE)
    )

    # Settle on a known surface before deciding. Without this, a non-waiting
    # is_visible() check on a not-yet-rendered page can race: pressing the modal
    # shortcut on the empty-first-run page (where it is disabled, and where the
    # inline form is the create surface) would open the modal OVER the inline form
    # and leave its overlay stuck. Wait until a create surface is showing (inline
    # form or already-open modal), the empty-first-run page is up, we are on a
    # workspace (chat panel), parked on Settings, or sitting on the Home list.
    #
    # ``.first`` is required: these surfaces OVERLAP (the empty-first-run page shows
    # both EMPTY_FIRST_RUN_PAGE and, once its form loads, NEW_WORKSPACE_CREATE_BUTTON),
    # so the bare ``or_`` chain resolves to >1 element and a strict-mode
    # ``to_be_visible()`` raises "resolved to N elements". ``.first`` makes the wait
    # mean "at least one of these surfaces is visible", which is the intent.
    expect(
        create_button.or_(chat_panel).or_(workspace_shell).or_(settings_page).or_(empty_first_run).or_(home_list).first
    ).to_be_visible(timeout=45_000)
    # Parked on Settings (no create affordance) — route Home, which settles on a
    # definite Home surface: the empty-first-run inline form (no workspaces) or the
    # Home workspace list. navigate_to_home_page waits for Home to land, so no extra
    # wait is needed here.
    if settings_page.is_visible():
        navigate_to_home_page(page)
    if create_button.is_visible():
        return

    # On the empty-first-run page the inline form IS the create surface, but its
    # create button mounts only after the form loads projects — and the modal
    # shortcut (Cmd/Meta+T) is disabled here, so falling through to it
    # would hang. Wait for the inline create button to appear instead.
    if empty_first_run.is_visible():
        expect(create_button).to_be_visible(timeout=45_000)
        return

    # No create surface yet — a workspace (chat panel) or the Home list. Open the
    # modal via the new_workspace keybinding (Cmd/Meta+T), which is mounted on every
    # route. The empty-first-run case already returned above via the inline button.
    open_new_workspace_modal(page)


def reset_active_panel_to_files(page: Page) -> None:
    """Reveal the Files panel in the workspace's seeded left section.

    An earlier step in the same test may have moved Files out of the left section
    (e.g. dragged it to the right) or activated a different tab there, so this
    expands the left section and re-activates the Files tab when it is present, and
    no-ops when it is not. Callers must already be on an open workspace — the left
    section (and ``expand_section``'s workspace-header toggle) only exist there.
    ``expand_section`` is idempotent and rides out header re-render churn on its
    own, so no extra guarding is needed here.
    """
    left = PlaywrightWorkspaceSection(page, "left")
    left.expand_section()
    files_tab = left.get_panel_tab("files")
    if files_tab.count() > 0:
        files_tab.click()


_MAX_WORKSPACE_DELETE_ITERATIONS = 50


def delete_all_workspaces_via_ui(page: Page) -> None:
    """Delete every workspace through the Home page workspace list.

    Workspaces live in the sidebar + Home list now (no tab strip); deleting each
    Home row via its inline delete button + confirmation removes them all and
    lands on the empty first-run state.
    """
    # Dismiss any open popover/context menu that might intercept clicks.
    page.keyboard.press("Escape")

    confirm_button = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
    confirm_dialog = page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)

    navigate_to_home_page(page)

    # Delete each workspace from the Home page workspace list.
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
    """Create a workspace and agent through the new-workspace UI.

    Opens the new-workspace modal (or uses the inline empty-first-run form when
    no workspaces exist yet) via ``open_new_workspace_form``, fills in the
    workspace name, clicks create, then waits for the agent chat page to appear.

    The new-workspace form has no model selector, so the model is switched on the
    chat panel once the workspace is ready.

    When *prompt* is provided, this helper leaves the creation form's own prompt
    field empty and sends *prompt* through the chat input after the workspace is
    created, so both creation surfaces (the new-workspace modal and the inline
    empty-first-run form, which share the same prompt-as-first-message field)
    behave identically.

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

    open_new_workspace_form(sculptor_page)

    # The same name/mode/agent-type fields and create button back both creation
    # surfaces (the new-workspace modal and the inline empty-first-run form); they
    # differ only in that the inline form pre-seeds the prompt (cleared below).
    submit_button, is_inline_form = get_workspace_creation_button(sculptor_page)

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

    # The empty-first-run inline form seeds the prompt with `/sculptor:help`; clear
    # it so the first agent is created promptless and this helper sends `prompt` as
    # the first chat message below (matching the modal flow) — otherwise the agent
    # would receive both the prefill and the test's prompt.
    if is_inline_form:
        sculptor_page.get_by_test_id(ElementIDs.NEW_WORKSPACE_PROMPT_TEXTAREA).fill("")

    # A WORKTREE/CLONE create needs a source branch (the base ref to fork the
    # worktree or clone from). The form derives it from the project's repo info
    # (`sourceBranch = repoInfo.currentBranch`), which loads on a SEPARATE request
    # from the branch-name preview. The submit button only gates on the branch
    # NAME being populated — NOT on repo info — so it can go enabled while the
    # source branch is still unresolved. Submitting in that window sends a create
    # with no `source_branch`, the backend rejects it with 400 ("source_branch is
    # required for WORKTREE workspaces"), and the form stays put, so the chat panel
    # awaited below never mounts and this helper times out. The source-branch
    # selector renders only once repo info has loaded, so waiting for it here
    # guarantees the create carries a source branch before we click.
    expect(sculptor_page.get_by_test_id(ElementIDs.BRANCH_SELECTOR)).to_be_visible(timeout=45_000)

    # Wait for the submit button to be enabled — the worktree-mode branch-name
    # preview has populated the input (the form gates submit on a non-empty branch
    # name in worktree mode).
    expect(submit_button).to_be_enabled()

    # Click create workspace
    submit_button.click()

    # When created via the modal, its overlay backdrop lingers through the close
    # animation and intercepts pointer events on the workspace beneath (e.g. the model
    # selector). Wait for the dialog to fully close before interacting. The inline
    # first-run form has no dialog, so this resolves instantly there.
    expect(sculptor_page.get_by_test_id(ElementIDs.NEW_WORKSPACE_DIALOG)).to_have_count(0, timeout=60_000)

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
    """Add an agent panel to the center section and wait until the new agent is
    the active one, with a chat input ready to receive a message.

    Returns a ``PlaywrightTaskPage`` bound to the new (now-active) agent.

    Adding an agent navigates to it only after an async create request
    resolves, but the panel-tab count flips to N+1 as soon as the agent-list
    query refreshes — which can happen before that navigation lands.  Callers
    must not type into the chat input until the switch completes, or the text
    lands in the outgoing agent's editor (or no editor, mid-remount).  Waiting
    for the URL to point at a different agent id is the settle signal.
    """
    task_page = PlaywrightTaskPage(page=page)
    previous_agent_id = task_page.get_task_id()
    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    existing_tab_count = panel_tabs.get_panel_tabs().count()

    create_agent_panel(page, section="center")
    expect(panel_tabs.get_panel_tabs()).to_have_count(existing_tab_count + 1)

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
    """Open Settings the way a user does — click the sidebar Settings link.

    The Settings link lives in the persistent sidebar (``AppShell`` renders it
    on every in-app route, and the empty first-run page mounts its own copy),
    so it is reachable from any state this helper is called from. Clicking
    routes via React Router with no document reload, so it keeps the WebSocket
    connection alive and avoids re-fetching ``index.html`` (and its assets)
    under the ``sculptor://app`` origin, where the built renderer references
    assets via absolute paths.

    The click is retried until the settings page actually renders. A single
    click can lose a race with an in-flight imperative redirect: deleting the
    last workspace makes WorkspacePage queue a ``navigate("/ws/new/<uuid>")``
    that may commit *after* our navigation and bounce us off ``/settings``.
    Re-clicking from the now-settled state lands cleanly — the redirect only
    fires while WorkspacePage is mounted, so once we reach Settings nothing
    redirects away again.
    """
    settings_button = page.get_by_test_id(ElementIDs.SIDEBAR_SETTINGS_LINK)
    settings_page_marker = page.get_by_test_id(ElementIDs.SETTINGS_PAGE)

    def _click_into_settings() -> None:
        # Inside the retry body: this helper also runs during per-test cleanup
        # (_delete_extra_projects_via_ui) against the PREVIOUS test's end
        # state, where the sidebar may be collapsed — its Settings link is then
        # unmounted, not just hidden — and the shell may still be churning.
        ensure_sidebar_expanded(page)
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

    # Land on a neutral Home surface after deletion — rather than leaving the
    # Settings page (or a lingering create surface) up for the caller.
    navigate_to_home_page(page)


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
    """Navigate to the Home page and back to force Jotai store reinitialization.

    The Sculptor frontend caches state in Jotai atoms that are initialized from
    localStorage on first load.  A hash-only navigation within the SPA does not
    unload/reload atoms.  By navigating to a different route (``#/home``) and
    then back, we force the atoms to reinitialize from whatever values are
    currently in localStorage.
    """
    current_url = page.url
    base_url = current_url.split("#")[0].rstrip("/")
    page.goto(f"{base_url}#/home")
    _expect_home_landed(page)
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


def wait_for_workspace_list_loaded(page: Page) -> None:
    """Wait until the frontend's workspace list has finished its initial load.

    Global keyboard shortcuts and every command-palette open path no-op while
    ``areGlobalShortcutsDisabledAtom`` is set, and it stays set while the
    workspace list is still loading (``undefined``) — not just while it is
    empty. The empty first-run page is deliberately NOT rendered during that
    load window (so it never flashes), which means a momentary
    ``EMPTY_FIRST_RUN_PAGE.is_visible()`` probe — e.g. the one inside
    ``ensure_workspace_exists`` — cannot distinguish "list still loading" from
    "list loaded with workspaces", and on a slow runner it lands in the load
    window, skips workspace creation, and every later palette open / shortcut
    press is silently suppressed. Wait for one of the two loaded-list signals
    before deciding anything: a sidebar workspace row (loaded, non-empty) or
    the empty first-run page (loaded, empty).
    """
    workspace_rows = page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)
    empty_first_run = page.get_by_test_id(ElementIDs.EMPTY_FIRST_RUN_PAGE)
    expect(workspace_rows.or_(empty_first_run).first).to_be_visible()


def create_zero_agent_workspace(page: Page, *, description: str | None = None, source_branch: str = "testing") -> str:
    """Create a WORKTREE workspace with NO agent and navigate to it, returning its id.

    The redesign relaxes the old "≥1 agent" invariant, so a
    workspace can exist with an empty center section. This drives that state via
    the backend API — ``POST /api/v1/workspaces`` creates the workspace WITHOUT
    an agent (agents are a separate ``/agents`` POST), so no agent is ever
    created — then navigates to ``/ws/<id>`` with a hash change so the WebSocket
    stays alive (mirroring ``navigate_to_workspace_without_agent``).

    Resolves the active project and a unique branch name (via the same
    ``preview-branch-name`` endpoint the Add Workspace form uses) so the worktree
    branch never collides across repeated calls.
    """
    base_url = page.url.split("#")[0].rstrip("/")

    projects_response = request_with_retry(page.request.get, f"{base_url}/api/v1/projects/active")
    assert projects_response.ok, f"list active projects failed: {projects_response.status} {projects_response.text()}"
    projects = projects_response.json()
    assert projects, "no active project to create a zero-agent workspace in"
    project_id = projects[0]["objectId"]

    workspace_name = description or f"Zero Agent WS {next(_workspace_name_counter)}"
    preview_response = request_with_retry(
        page.request.get,
        f"{base_url}/api/v1/workspaces/preview-branch-name",
        params={"project_id": project_id, "workspace_name": workspace_name, "mode": "WORKTREE"},
    )
    assert preview_response.ok, f"preview-branch-name failed: {preview_response.status} {preview_response.text()}"
    branch_name = preview_response.json()["branchName"]

    create_response = request_with_retry(
        page.request.post,
        f"{base_url}/api/v1/workspaces",
        data={
            "projectId": project_id,
            "initializationStrategy": "WORKTREE",
            "sourceBranch": source_branch,
            "requestedBranchName": branch_name,
            "description": workspace_name,
        },
    )
    assert create_response.ok, f"create workspace failed: {create_response.status} {create_response.text()}"
    workspace_id = create_response.json()["objectId"]

    navigate_to_workspace_without_agent(page, workspace_id)
    return workspace_id


def dispatch_modified_shortcuts_in_one_task(page: Page, shortcuts: Sequence[tuple[str, str]]) -> list[str]:
    """Fire Cmd/Ctrl-modified keydown shortcuts back-to-back within a single task.

    Each ``(key, code)`` pair is dispatched on ``window`` as a keydown carrying
    the platform's primary modifier (Cmd on macOS, Ctrl elsewhere), with no yield
    to the event loop between dispatches.  React therefore cannot re-render or
    re-register window listeners in between, which deterministically exercises
    handlers that would otherwise read stale closed-over state only on a rapid
    second keypress.

    Returns ``window.location.hash`` captured before the first dispatch and after
    each one, so a navigation test can assert how the shortcuts moved the route
    before the app had a chance to settle.

    ``page.evaluate`` is unavoidable here: ``page.keyboard.press`` delivers each
    press as a separate input event, letting the event loop (and React) run in
    between, which would mask exactly the timing this reproduces.
    """
    return page.evaluate(
        """(shortcuts) => {
            const isMac = window.sculptor?.platform === "darwin" || navigator.platform.startsWith("Mac");
            const hashes = [window.location.hash];
            for (const [key, code] of shortcuts) {
              window.dispatchEvent(new KeyboardEvent("keydown", {
                key, code,
                metaKey: isMac, ctrlKey: !isMac, altKey: false, shiftKey: false,
                bubbles: true, cancelable: true,
              }));
              hashes.push(window.location.hash);
            }
            return hashes;
        }""",
        [list(shortcut) for shortcut in shortcuts],
    )


def get_electron_app_version(page: Page) -> str:
    """Return the Electron ``app.getVersion()`` string from the running instance.

    ``electron-updater`` compares the manifest version against this value to
    decide whether an update is available.  In dev mode it returns ``"0.0.0"``
    (from ``package.json``); in packaged builds it returns the real semver set
    during packaging.
    """
    version: str = page.evaluate("window.sculptor.getAppVersion()")
    return version
