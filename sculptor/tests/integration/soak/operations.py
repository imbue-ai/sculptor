"""Concrete soak operations and recovery actions.

Each operation is small and self-contained. ``is_available`` is a cheap
DOM probe — the runner's "reactive" half — so we never try an operation
that has no chance of succeeding in the current UI state.

Naming follows Sculptor's UI vocabulary: **workspaces** (the tabs) and
**agents** (the chats inside them). Operations are deliberately small;
combine via a future compound :class:`Operation` if you need scripted
sequences.
"""

from __future__ import annotations

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.utils import get_playwright_modifier_key
from tests.integration.soak.framework import Operation
from tests.integration.soak.framework import OperationContext
from tests.integration.soak.framework import RecoveryAction

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
# Workspace lifecycle
# ---------------------------------------------------------------------------


_MAX_OPEN_WORKSPACES = 5

_WRITE_FILE_PROMPT_TEMPLATE = 'fake_claude:write_file `{{"file_path": "soak_iter_{iteration:05d}.txt", "content": "soak iteration {iteration:05d}"}}`'  # noqa: E501


class CreateWorkspaceWriteFileOp(Operation):
    """Create a workspace whose agent writes a single file via FakeClaude."""

    name = "create_workspace_write_file"
    weight = 0.5  # heavy op — keep the cadence reasonable

    def is_available(self, ctx: OperationContext) -> bool:
        tabs = ctx.page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
        return tabs.count() < _MAX_OPEN_WORKSPACES

    def execute(self, ctx: OperationContext) -> None:
        prompt = _WRITE_FILE_PROMPT_TEMPLATE.format(iteration=ctx.iteration)
        start_task_and_wait_for_ready(
            sculptor_page=ctx.page,
            prompt=prompt,
            wait_for_agent_to_finish=True,
        )


class NavigateWorkspaceTabOp(Operation):
    """Click a randomly-chosen workspace tab.

    Lets the random walk leave the home / add-workspace pages and exercise
    workspace-internal UI. Picks any tab — including the currently active
    one — so a "click currently active tab" no-op is part of the
    distribution; that's fine, it stresses tab state handling too.
    """

    name = "navigate_workspace_tab"
    weight = 1.0

    def is_available(self, ctx: OperationContext) -> bool:
        return ctx.page.get_by_test_id(ElementIDs.WORKSPACE_TAB).count() > 0

    def execute(self, ctx: OperationContext) -> None:
        tabs = ctx.page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
        count = tabs.count()
        if count == 0:
            # Race between is_available and execute — record and bail.
            ctx.record_event("navigate_workspace_tab_vanished")
            return
        index = ctx.rng.randrange(count)
        ctx.record_event("navigate_workspace_tab_pick", index=index, total=count)
        tabs.nth(index).click()


class WorkspaceDeletionOp(Operation):
    """Right-click a workspace tab, choose Delete, and confirm the dialog."""

    name = "workspace_deletion"
    weight = 0.4

    def is_available(self, ctx: OperationContext) -> bool:
        # Only delete when there are at least two — keeps the cap from
        # ratcheting all the way to zero in one chaos burst and leaves
        # something for the other ops to act on.
        return ctx.page.get_by_test_id(ElementIDs.WORKSPACE_TAB).count() >= 2

    def execute(self, ctx: OperationContext) -> None:
        tabs = ctx.page.get_by_test_id(ElementIDs.WORKSPACE_TAB)
        count = tabs.count()
        if count < 2:
            ctx.record_event("workspace_deletion_vanished")
            return
        index = ctx.rng.randrange(count)
        ctx.record_event("workspace_deletion_pick", index=index, total=count)

        target_tab = tabs.nth(index)
        target_tab.click(button="right")

        delete_item = ctx.page.get_by_test_id(ElementIDs.TAB_CONTEXT_MENU_DELETE)
        expect(delete_item).to_be_visible(timeout=5_000)
        delete_item.click()

        confirm_button = ctx.page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_CONFIRM)
        expect(confirm_button).to_be_visible(timeout=5_000)
        confirm_button.click()

        confirm_dialog = ctx.page.get_by_test_id(ElementIDs.DELETE_CONFIRMATION_DIALOG)
        expect(confirm_dialog).to_be_hidden(timeout=10_000)


# ---------------------------------------------------------------------------
# Cheap navigation / UI ops
# ---------------------------------------------------------------------------


class NavigateHomeOp(Operation):
    """Navigate to the home page and assert the workspace list shows up."""

    name = "navigate_home"
    weight = 1.0

    def execute(self, ctx: OperationContext) -> None:
        navigate_to_home_page(ctx.page)


class OpenCloseCommandPaletteOp(Operation):
    """Open the command palette with Cmd+K, then close with Escape."""

    name = "open_close_command_palette"
    weight = 1.5

    def is_available(self, ctx: OperationContext) -> bool:
        return ctx.page.get_by_test_id(ElementIDs.TOP_BAR).is_visible()

    def execute(self, ctx: OperationContext) -> None:
        mod = get_playwright_modifier_key()
        ctx.page.keyboard.press(f"{mod}+k")
        # See PlaywrightProjectLayoutPage.press_keyboard_shortcut: macOS Chromium
        # can swallow the modifier keyup after a chord, so explicitly release.
        ctx.page.keyboard.up(mod)
        palette = ctx.page.get_by_test_id(ElementIDs.COMMAND_PALETTE)
        expect(palette).to_be_visible(timeout=5_000)
        ctx.page.keyboard.press("Escape")
        expect(palette).not_to_be_visible(timeout=5_000)


class OpenCloseSettingsOp(Operation):
    """Click the settings button, wait for the page, then go home."""

    name = "open_close_settings"
    weight = 0.8

    def is_available(self, ctx: OperationContext) -> bool:
        return ctx.page.get_by_test_id(ElementIDs.SETTINGS_BUTTON).is_visible()

    def execute(self, ctx: OperationContext) -> None:
        ctx.page.get_by_test_id(ElementIDs.SETTINGS_BUTTON).click()
        expect(ctx.page.get_by_test_id(ElementIDs.SETTINGS_PAGE)).to_be_visible(timeout=10_000)
        navigate_to_home_page(ctx.page)


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
        return ctx.page.get_by_test_id(ElementIDs.TOP_BAR).is_visible()


# ---------------------------------------------------------------------------
# Global invariants — checked between every operation
# ---------------------------------------------------------------------------


def invariant_page_alive(ctx: OperationContext) -> None:
    """Hard-fail if the Playwright page has been closed underneath us."""
    ctx.hard_check("page_alive", lambda: _assert(not ctx.page.is_closed(), "page is closed"))


def invariant_top_bar_or_onboarding(ctx: OperationContext) -> None:
    """Hard-fail if neither the top bar nor onboarding is visible — the SPA is broken."""
    top_bar = ctx.page.get_by_test_id(ElementIDs.TOP_BAR)
    onboarding = ctx.page.get_by_test_id(ElementIDs.ONBOARDING_WELCOME_STEP)
    ctx.hard_check(
        "top_bar_or_onboarding_visible",
        lambda: expect(top_bar.or_(onboarding)).to_be_visible(timeout=5_000),
    )


def invariant_no_unexpected_error_toast(ctx: OperationContext) -> None:
    """Soft-flag if an error toast is currently visible (does not abort)."""
    toast = ctx.page.get_by_test_id(ElementIDs.TOAST)
    if toast.count() == 0 or not toast.first.is_visible():
        return
    text = toast.first.inner_text()
    ctx.soft_check("no_error_toast", lambda: _assert(False, f"toast visible: {text!r}"))


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


DEFAULT_OPERATIONS: list[Operation] = [
    IdleWaitOp(),
    CreateWorkspaceWriteFileOp(),
    NavigateWorkspaceTabOp(),
    WorkspaceDeletionOp(),
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
    invariant_top_bar_or_onboarding,
    invariant_no_unexpected_error_toast,
]
