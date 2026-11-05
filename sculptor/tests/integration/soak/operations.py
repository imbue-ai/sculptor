"""Concrete soak operations and recovery actions.

Each operation is small and self-contained. ``is_available`` is a cheap
DOM probe — the runner's "reactive" half — so we never try an operation
that has no chance of succeeding in the current UI state.

Naming follows Sculptor's UI vocabulary: **workspaces** (sidebar rows) and
**agents** (panel tabs inside a workspace's center section). Operations are
deliberately small; combine via a future compound :class:`Operation` if you
need scripted sequences.

The UI moved from a top-bar + tab-strip model to a sidebar rail
(``WORKSPACE_SIDEBAR``: home / Cmd-K / new-workspace links, workspace rows,
settings) plus per-section panels opened through the ``+`` add-panel dropdown.
These ops drive that model via the shared POM helpers
(``workspace_sidebar`` / ``add_panel_dropdown`` / ``panel_tab``) rather than
raw test ids, so they ride along with future test-id churn.
"""

from __future__ import annotations

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import create_agent_panel
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.playwright_utils import ensure_sidebar_expanded
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from tests.integration.soak.framework import Operation
from tests.integration.soak.framework import OperationContext
from tests.integration.soak.framework import RecoveryAction


def _app_shell_ready(page: Page) -> bool:
    """Whether the workspace shell (sidebar rail) is mounted.

    The sidebar root is hidden while collapsed (the rail is replaced by the
    expand icon), so accept either — both mean the in-app shell is up and its
    home / Cmd-K / settings affordances are reachable after an expand.
    """
    return (
        page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR).count() > 0
        or page.get_by_test_id(ElementIDs.SIDEBAR_EXPAND_ICON).count() > 0
    )


def _agent_tabs(page: Page):
    """Agent panel tabs in the center section (the successor to the tab strip)."""
    return PlaywrightPanelTabElement(page, "center").get_agent_tabs()


# ---------------------------------------------------------------------------
# Always-available baseline
# ---------------------------------------------------------------------------


class IdleWaitOp(Operation):
    """No-op that sleeps for a short, randomised interval.

    Guarantees the picker always has at least one available operation, so
    the runner can treat "nothing available" as a misconfiguration. Also
    gives the UI breathing room between bursts of activity.
    """

    name = "idle_wait"
    weight = 0.2

    def execute(self, ctx: OperationContext) -> None:
        millis = ctx.rng.randint(250, 1_500)
        ctx.record_event("idle_wait_ms", millis=millis)
        ctx.page.wait_for_timeout(millis)


# ---------------------------------------------------------------------------
# Workspace lifecycle (sidebar rows)
# ---------------------------------------------------------------------------


_MAX_OPEN_WORKSPACES = 5

_WRITE_FILE_PROMPT_TEMPLATE = 'fake_claude:write_file `{{"file_path": "soak_iter_{iteration:05d}.txt", "content": "soak iteration {iteration:05d}"}}`'  # noqa: E501


class CreateWorkspaceWriteFileOp(Operation):
    """Create a workspace whose agent writes a single file via FakeClaude."""

    name = "create_workspace_write_file"
    weight = 0.5  # heavy op — keep the cadence reasonable

    def is_available(self, ctx: OperationContext) -> bool:
        rows = ctx.page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW)
        return rows.count() < _MAX_OPEN_WORKSPACES

    def execute(self, ctx: OperationContext) -> None:
        prompt = _WRITE_FILE_PROMPT_TEMPLATE.format(iteration=ctx.iteration)
        start_task_and_wait_for_ready(
            sculptor_page=ctx.page,
            prompt=prompt,
            wait_for_agent_to_finish=True,
        )


class NavigateWorkspaceOp(Operation):
    """Click a randomly-chosen workspace row in the sidebar.

    Lets the random walk move between workspaces and exercise
    workspace-internal UI. Picks any row — including the active one — so a
    "click currently active workspace" no-op is part of the distribution;
    that's fine, it stresses row/route state handling too.
    """

    name = "navigate_workspace"
    weight = 1.0

    def is_available(self, ctx: OperationContext) -> bool:
        return ctx.page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW).count() > 0

    def execute(self, ctx: OperationContext) -> None:
        ensure_sidebar_expanded(ctx.page)
        rows = get_workspace_sidebar(ctx.page).get_workspace_rows()
        count = rows.count()
        if count == 0:
            # Race between is_available and execute — record and bail.
            ctx.record_event("navigate_workspace_vanished")
            return
        index = ctx.rng.randrange(count)
        ctx.record_event("navigate_workspace_pick", index=index, total=count)
        navigate_to_workspace(ctx.page, index)


class WorkspaceDeletionOp(Operation):
    """Right-click a sidebar workspace row, choose Delete, and confirm the dialog."""

    name = "workspace_deletion"
    weight = 0.4
    cooldown_iterations = 2  # destructive — space out

    def is_available(self, ctx: OperationContext) -> bool:
        # Only delete when there are at least two — keeps the count from
        # ratcheting all the way to zero in one chaos burst and leaves
        # something for the other ops to act on.
        return ctx.page.get_by_test_id(ElementIDs.SIDEBAR_WORKSPACE_ROW).count() >= 2

    def execute(self, ctx: OperationContext) -> None:
        ensure_sidebar_expanded(ctx.page)
        sidebar = get_workspace_sidebar(ctx.page)
        rows = sidebar.get_workspace_rows()
        count = rows.count()
        if count < 2:
            ctx.record_event("workspace_deletion_vanished")
            return
        index = ctx.rng.randrange(count)
        ctx.record_event("workspace_deletion_pick", index=index, total=count)
        sidebar.delete_workspace_via_context_menu(rows.nth(index))
        expect(sidebar.get_delete_confirmation_dialog()).to_be_hidden(timeout=10_000)


# ---------------------------------------------------------------------------
# Agent-view ops (center-section panel tabs)
# ---------------------------------------------------------------------------


_LONG_AGENT_PROMPT_SECONDS = (15, 30, 60)


class SendLongAgentPromptOp(Operation):
    """Fire a long-running FakeClaude sleep prompt into the current agent and don't wait.

    The point is to pile concurrent agent work onto the backend while the
    soak keeps moving — closes, deletions, and adds during a busy turn are
    where the gnarliest races live.
    """

    name = "send_long_agent_prompt"
    weight = 0.8

    def is_available(self, ctx: OperationContext) -> bool:
        return ctx.page.get_by_test_id(ElementIDs.CHAT_INPUT).is_visible()

    def execute(self, ctx: OperationContext) -> None:
        seconds = ctx.rng.choice(_LONG_AGENT_PROMPT_SECONDS)
        prompt = f'fake_claude:sleep `{{"seconds": {seconds}}}`'
        ctx.record_event("send_long_agent_prompt", seconds=seconds)
        chat_input = ctx.page.get_by_test_id(ElementIDs.CHAT_INPUT)
        type_into_tiptap(ctx.page, chat_input, prompt)
        ctx.page.get_by_test_id(ElementIDs.SEND_BUTTON).click()


class CloseCurrentAgentTabOp(Operation):
    """Close a randomly-chosen agent panel tab via its X button + confirm dialog.

    Exercises the path that auto-creates a new agent when the last one is
    closed, AND the "close one of N" path with multiple agents.
    """

    name = "close_current_agent_tab"
    weight = 0.3
    cooldown_iterations = 3  # destructive — leave room for the workspace to settle

    def is_available(self, ctx: OperationContext) -> bool:
        return _agent_tabs(ctx.page).count() >= 1

    def execute(self, ctx: OperationContext) -> None:
        panel_tabs = PlaywrightPanelTabElement(ctx.page, "center")
        agent_tabs = panel_tabs.get_agent_tabs()
        count = agent_tabs.count()
        if count == 0:
            ctx.record_event("close_agent_tab_vanished")
            return
        index = ctx.rng.randrange(count)
        ctx.record_event("close_agent_tab_pick", index=index, total=count)
        tab = agent_tabs.nth(index)
        tab.click()
        # The close (X) test id is panel-id-suffixed, so match it under the tab.
        close_button = panel_tabs.get_tab_close_button_of(tab)
        expect(close_button).to_be_visible(timeout=5_000)
        close_button.click()
        # Closing an agent opens a delete/close confirmation.
        confirm_dialog = ctx.page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)
        if confirm_dialog.is_visible():
            ctx.page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM).click()
            expect(confirm_dialog).to_be_hidden(timeout=10_000)


class AddAgentToWorkspaceOp(Operation):
    """Add another agent to the current workspace via the center section `+` dropdown."""

    name = "add_agent_to_workspace"
    weight = 0.5

    def is_available(self, ctx: OperationContext) -> bool:
        # We're inside a workspace iff its center section has an agent tab.
        return _agent_tabs(ctx.page).count() >= 1

    def execute(self, ctx: OperationContext) -> None:
        before = _agent_tabs(ctx.page).count()
        # Fire and forget — don't wait for the new agent to ready up.
        create_agent_panel(ctx.page, "center")
        ctx.record_event("add_agent_to_workspace", before_count=before)


# Single-instance panels worth opening, paired with the section their registry
# entry seeds/defaults into (see frontend panelRegistry.ts). open_panel reveals
# a seeded panel in place or opens a non-seeded one into the given section.
_PANEL_TARGETS = (
    ("files", "left"),
    ("changes", "left"),
    ("commits", "left"),
    ("actions", "right"),
    ("skills", "right"),
    ("notes", "right"),
)


class OpenRandomPanelOp(Operation):
    """Open a random single-instance panel via the section add-panel dropdown."""

    name = "open_random_panel"
    weight = 0.6

    def is_available(self, ctx: OperationContext) -> bool:
        # Panels are workspace-scoped; a center agent tab means a workspace is open.
        return _agent_tabs(ctx.page).count() >= 1

    def execute(self, ctx: OperationContext) -> None:
        panel_id, section = ctx.rng.choice(_PANEL_TARGETS)
        ctx.record_event("open_random_panel", panel=panel_id, section=section)
        open_panel(ctx.page, panel_id, section)


class StopRunningAgentOp(Operation):
    """Click the in-pill Stop button while an agent is mid-turn.

    Heavy weight + cooldown: the pill is only visible while an agent is
    cancellable, so opportunities are scarce. When they come up we want to
    grab one, but not every consecutive tick of the same busy turn.
    """

    name = "stop_running_agent"
    weight = 2.5  # bumped so we actually pick it when the rare opportunity appears
    cooldown_iterations = 5  # but don't spam-stop the same turn

    def is_available(self, ctx: OperationContext) -> bool:
        # STATUS_PILL_STOP only renders while the agent is cancellable, so
        # its visibility is the right gate.
        stop = ctx.page.get_by_test_id(ElementIDs.STATUS_PILL_STOP)
        return stop.count() > 0 and stop.first.is_visible()

    def execute(self, ctx: OperationContext) -> None:
        ctx.record_event("stop_running_agent")
        ctx.page.get_by_test_id(ElementIDs.STATUS_PILL_STOP).first.click()


# ---------------------------------------------------------------------------
# Cheap navigation / UI ops (sidebar links)
# ---------------------------------------------------------------------------


class NavigateHomeOp(Operation):
    """Navigate to the home page via the sidebar Home link."""

    name = "navigate_home"
    weight = 0.3

    def execute(self, ctx: OperationContext) -> None:
        navigate_to_home_page(ctx.page)


class OpenCloseCommandPaletteOp(Operation):
    """Open the command palette via the sidebar Cmd-K link, then close with Escape."""

    name = "open_close_command_palette"
    weight = 0.3

    def is_available(self, ctx: OperationContext) -> bool:
        return _app_shell_ready(ctx.page)

    def execute(self, ctx: OperationContext) -> None:
        ensure_sidebar_expanded(ctx.page)
        get_workspace_sidebar(ctx.page).get_cmdk_link().click()
        palette = ctx.page.get_by_test_id(ElementIDs.COMMAND_PALETTE)
        expect(palette).to_be_visible(timeout=5_000)
        ctx.page.keyboard.press("Escape")
        expect(palette).not_to_be_visible(timeout=5_000)


class OpenCloseSettingsOp(Operation):
    """Click the sidebar Settings link, wait for the page, then go home."""

    name = "open_close_settings"
    weight = 0.8

    def is_available(self, ctx: OperationContext) -> bool:
        return _app_shell_ready(ctx.page)

    def execute(self, ctx: OperationContext) -> None:
        ensure_sidebar_expanded(ctx.page)
        get_workspace_sidebar(ctx.page).get_settings_link().click()
        expect(ctx.page.get_by_test_id(ElementIDs.SETTINGS_PAGE)).to_be_visible(timeout=10_000)
        navigate_to_home_page(ctx.page)


# ---------------------------------------------------------------------------
# File browser / file viewer ops
# ---------------------------------------------------------------------------


class OpenFileFromBrowserOp(Operation):
    """Open the Files panel and click a random *file* row, viewing it in the diff panel.

    Folder rows carry ``aria-expanded``; file rows don't — that's how we pick
    only files. The op opens the Files panel itself (seeded into the left
    section), so it only needs a workspace to be open.
    """

    name = "open_file_from_browser"
    weight = 1.0

    def is_available(self, ctx: OperationContext) -> bool:
        return _agent_tabs(ctx.page).count() >= 1

    def execute(self, ctx: OperationContext) -> None:
        open_panel(ctx.page, "files", "left")
        panel = ctx.page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
        expect(panel).to_be_visible(timeout=10_000)
        rows = panel.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW)
        count = rows.count()
        if count == 0:
            ctx.record_event("open_file_no_rows")
            return
        file_indices = [i for i in range(count) if rows.nth(i).get_attribute("aria-expanded") is None]
        if not file_indices:
            # Only folders visible — expand a random one so files appear next time.
            index = ctx.rng.randrange(count)
            ctx.record_event("open_file_expanded_folder", index=index, total=count)
            rows.nth(index).click()
            return
        index = ctx.rng.choice(file_indices)
        row = rows.nth(index)
        path = row.get_attribute("data-tree-path")
        ctx.record_event("open_file_pick", path=path, index=index, total=count)
        row.click()
        expect(ctx.page.get_by_test_id(ElementIDs.DIFF_PANEL)).to_be_visible(timeout=10_000)


class ScrollOpenFileOp(Operation):
    """Scroll up/down inside the currently-open file view via mouse wheel."""

    name = "scroll_open_file"
    weight = 1.0

    def is_available(self, ctx: OperationContext) -> bool:
        # Requires a file to actually be rendering in the diff panel — any of
        # the three content surfaces (read-only preview, unified, split).
        if not ctx.page.get_by_test_id(ElementIDs.DIFF_PANEL).is_visible():
            return False
        return any(
            ctx.page.get_by_test_id(testid).count() > 0 and ctx.page.get_by_test_id(testid).first.is_visible()
            for testid in (ElementIDs.READ_ONLY_PREVIEW, ElementIDs.DIFF_VIEW_UNIFIED, ElementIDs.DIFF_VIEW_SPLIT)
        )

    def execute(self, ctx: OperationContext) -> None:
        for testid in (ElementIDs.READ_ONLY_PREVIEW, ElementIDs.DIFF_VIEW_UNIFIED, ElementIDs.DIFF_VIEW_SPLIT):
            content = ctx.page.get_by_test_id(testid)
            if content.count() > 0 and content.first.is_visible():
                break
        else:
            ctx.record_event("scroll_open_file_vanished")
            return
        content.first.hover()
        delta = ctx.rng.randint(200, 1_500)
        ctx.record_event("scroll_open_file", testid=str(testid), delta=delta)
        ctx.page.mouse.wheel(0, delta)
        # Occasionally scroll back up so we exercise both directions.
        if ctx.rng.random() < 0.5:
            ctx.page.mouse.wheel(0, -delta)


# ---------------------------------------------------------------------------
# Chaos
# ---------------------------------------------------------------------------


_CHAOS_DENYLIST_SUBSTRINGS = (
    "DELETE",
    "REMOVE",
    "LOGOUT",
    "SIGN_OUT",
    "RESET",
    "DESTROY",
    "TRASH",
    "UNINSTALL",
    "CHECK_FOR_UPDATES",
    "INSTALL_UPDATE",
)


_VISIBLE_TESTIDS_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('[data-testid]')) {
        if (el.offsetWidth <= 0 || el.offsetHeight <= 0) continue;
        const rect = el.getBoundingClientRect();
        if (rect.bottom < 0 || rect.right < 0) continue;
        out.push(el.getAttribute('data-testid'));
    }
    return out;
}"""


class ChaosClickOp(Operation):
    """Pick a random visible element by test id and click it."""

    name = "chaos_click"
    weight = 0.3
    cooldown_iterations = 2  # chaos is disruptive — leave gaps for invariants to settle

    def execute(self, ctx: OperationContext) -> None:
        testids: list[str] = ctx.page.evaluate(_VISIBLE_TESTIDS_JS)
        safe = [tid for tid in testids if not any(token in tid.upper() for token in _CHAOS_DENYLIST_SUBSTRINGS)]
        if not safe:
            ctx.record_event("chaos_no_safe_target")
            return
        chosen = ctx.rng.choice(safe)
        ctx.record_event("chaos_choice", chosen_testid=chosen, candidate_count=len(safe))
        target = ctx.page.get_by_test_id(chosen).first
        # Bounded timeout: chaos is allowed to fail; the runner will recover.
        target.click(timeout=2_000)


# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------


class NavigateHomeRecovery(RecoveryAction):
    """Dismiss any modal and navigate back to the home page."""

    name = "navigate_home"

    def apply(self, ctx: OperationContext) -> bool:
        try:
            ctx.page.keyboard.press("Escape")
        except Exception:
            pass
        navigate_to_home_page(ctx.page)
        return _app_shell_ready(ctx.page)


# ---------------------------------------------------------------------------
# Global invariants — checked between every operation
# ---------------------------------------------------------------------------


def invariant_page_alive(ctx: OperationContext) -> None:
    """Hard-fail if the Playwright page has been closed underneath us."""
    ctx.hard_check("page_alive", lambda: _assert(not ctx.page.is_closed(), "page is closed"))


def invariant_shell_or_onboarding(ctx: OperationContext) -> None:
    """Hard-fail if neither the workspace sidebar nor onboarding is visible — the SPA is broken."""
    sidebar = ctx.page.get_by_test_id(ElementIDs.WORKSPACE_SIDEBAR)
    expand_icon = ctx.page.get_by_test_id(ElementIDs.SIDEBAR_EXPAND_ICON)
    onboarding = ctx.page.get_by_test_id(ElementIDs.ONBOARDING_WELCOME_STEP)
    ctx.hard_check(
        "shell_or_onboarding_visible",
        lambda: expect(sidebar.or_(expand_icon).or_(onboarding)).to_be_visible(timeout=5_000),
    )


# Toast variants that indicate something went wrong. Values match the
# ToastType const in frontend/src/components/Toast.tsx, exposed on the DOM as
# data-toast-type. "default" and "success" (e.g. "Agent stopped successfully")
# are benign.
_ERROR_TOAST_TYPES = ("error", "warning", "errorProminent")


def invariant_no_unexpected_error_toast(ctx: OperationContext) -> None:
    """Soft-flag if an error/warning toast is currently visible (does not abort)."""
    toasts = ctx.page.get_by_test_id(ElementIDs.TOAST)
    for i in range(toasts.count()):
        toast = toasts.nth(i)
        if not toast.is_visible():
            continue
        toast_type = toast.get_attribute("data-toast-type")
        if toast_type not in _ERROR_TOAST_TYPES:
            continue
        message = f"{toast_type} toast visible: {toast.inner_text()!r}"
        ctx.soft_check("no_error_toast", lambda message=message: _assert(False, message))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


DEFAULT_OPERATIONS: list[Operation] = [
    IdleWaitOp(),
    CreateWorkspaceWriteFileOp(),
    NavigateWorkspaceOp(),
    WorkspaceDeletionOp(),
    SendLongAgentPromptOp(),
    CloseCurrentAgentTabOp(),
    AddAgentToWorkspaceOp(),
    OpenRandomPanelOp(),
    StopRunningAgentOp(),
    OpenFileFromBrowserOp(),
    ScrollOpenFileOp(),
    NavigateHomeOp(),
    OpenCloseCommandPaletteOp(),
    OpenCloseSettingsOp(),
    ChaosClickOp(),
]

DEFAULT_RECOVERIES: list[RecoveryAction] = [
    NavigateHomeRecovery(),
]

DEFAULT_GLOBAL_INVARIANTS = [
    invariant_page_alive,
    invariant_shell_or_onboarding,
    invariant_no_unexpected_error_toast,
]
