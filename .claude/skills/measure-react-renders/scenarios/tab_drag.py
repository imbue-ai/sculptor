"""Scenario: Cross-section tab drag render cascade.

Measures re-renders while dragging the agent tab from the Center section's tab
strip across the Left section's strip (files / changes / commits), crossing
several tab boundaries so the insertion-index preview updates repeatedly.

The drag is cancelled with Escape before mouse-up, so the layout state is
untouched and the measurement is repeatable on the same instance.

Relies on the compact-layout default workspace layout: Left section visible
with three file-browser tabs, agent tab in the Center strip.
"""

import time

DESCRIPTION = "Cross-section tab drag render cascade"

TARGET_COMPONENTS = [
    # Section shell + extracted children (current); pre-split names (baseline)
    "PanelSection",
    "PanelSectionInner",
    "SectionTabBarInner",
    "SectionBodyInner",
    "SplittableSection",
    "SplittableSectionInner",
    "CompactLayout",
    "PanelDndProvider",
    "DragTabPreview",
    # Tab internals
    "TabBar",
    "SortableTab",
    "SortableTabContentInner",
    # Heavy panel content that must NOT re-render during a drag
    "AlphaChatInterface",
    "AlphaChatInterfaceInner",
    "ChatInput",
    "ChatPanelContent",
    "AgentPanel",
    "TerminalPanel",
    "FilesPanel",
    "FileBrowserPanel",
    "MasterDetailPanel",
]

MOVE_STEPS = 30


_ONBOARDING_FLAGS = (
    "hasDependenciesPassing",
    "has_dependencies_passing",
    "hasEmail",
    "has_email",
    "hasPrivacyConsent",
    "has_privacy_consent",
    "hasProject",
    "has_project",
)


def _patch_config_status(route):
    response = route.fetch()
    body = response.json()
    for key in _ONBOARDING_FLAGS:
        if key in body:
            body[key] = True
    route.fulfill(response=response, json=body)


def _bypass_onboarding_gate(page):
    """RequireOnboarding blocks the workspace behind a wizard whose
    installation step waits on a real dependency download — not viable on the
    throwaway perf backends. Force the config-status flags it checks instead;
    applied identically to baseline and current, so the comparison is fair."""
    page.route("**/api/v1/config/status*", _patch_config_status)


def setup(page, base_url, workspace_id, task_id):
    _bypass_onboarding_gate(page)
    # NOTE: no networkidle waits — the workspace page keeps long-lived
    # connections open, so networkidle never fires once it loads.
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("load")
    time.sleep(5)
    # Both strips must be present: the agent tab (drag source) and the Left
    # section's tabs (drag target).
    page.wait_for_selector('[data-testid^="panel-tab-agent:"]', timeout=30000)
    page.wait_for_selector('[data-testid="panel-tab-files"]', timeout=30000)
    time.sleep(2)


def action(page):
    agent_tab = page.locator('[data-testid^="panel-tab-agent:"]').first
    files_tab = page.locator('[data-testid="panel-tab-files"]')
    commits_tab = page.locator('[data-testid="panel-tab-commits"]')

    source = agent_tab.bounding_box()
    start = files_tab.bounding_box()
    end = commits_tab.bounding_box()
    if not source or not start or not end:
        raise RuntimeError("Could not resolve tab positions for the drag")

    src_x = source["x"] + source["width"] / 2
    src_y = source["y"] + source["height"] / 2

    page.mouse.move(src_x, src_y)
    page.mouse.down()
    # Exceed the PointerSensor's 5px activation distance.
    page.mouse.move(src_x + 8, src_y, steps=2)
    time.sleep(0.2)

    # Sweep across the Left strip from beyond the last tab back over the first,
    # crossing each tab's midpoint so the insertion preview flips repeatedly.
    sweep_from_x = end["x"] + end["width"] - 4
    sweep_to_x = start["x"] + 4
    strip_y = start["y"] + start["height"] / 2

    page.mouse.move(sweep_from_x, strip_y, steps=10)
    time.sleep(0.2)
    for i in range(MOVE_STEPS):
        t = (i + 1) / MOVE_STEPS
        x = sweep_from_x + (sweep_to_x - sweep_from_x) * t
        page.mouse.move(x, strip_y)
        time.sleep(0.05)
    time.sleep(0.3)

    # Cancel so zone state is unchanged and the run is repeatable.
    page.keyboard.press("Escape")
    time.sleep(0.2)
    page.mouse.up()
    time.sleep(0.5)
