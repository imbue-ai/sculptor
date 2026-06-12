"""Scenario: Workspace tab switching render cascade.

Measures re-renders when the user clicks between workspace tabs in the
WorkspaceTabs component. Tab switching navigates to a different workspace URL
and changes the active agent, causing WorkspacePage to mount new content.

This tests whether tab switching causes excessive re-renders in components
that should be stable across tab changes (sidebars, DockingLayout structure).
"""

import time

DESCRIPTION = "Workspace tab switching"

TARGET_COMPONENTS = [
    "WorkspacePage",
    "WorkspacePageContent",
    "DockingLayout",
    "LeftSidebar",
    "LeftSidebarInner",
    "RightSidebar",
    "RightSidebarInner",
    "ZoneContent",
    "ZoneContentInner",
    "DiffSplitContainer",
    "DiffSplitContainerInner",
    "AlphaChatInterface",
    "AlphaChatInterfaceInner",
    "ChatInput",
    "WorkspaceBanner",
    "WorkspaceTabs",
    "TopBar",
]


def _create_second_task(page, base_url):
    """Create a second task via the UI or API and return its task_id."""
    # Use fetch() inside the page to call the API directly
    result = page.evaluate("""async () => {
        const projectsRes = await fetch('/api/v1/projects');
        const projects = await projectsRes.json();
        const projectId = projects[0]?.objectId;
        if (!projectId) return null;
        const taskRes = await fetch(`/api/v1/projects/${projectId}/tasks`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                prompt: 'Say goodbye briefly',
                interface: 'API',
                model: 'CLAUDE-4-SONNET',
                mode: 'IN_PLACE'
            })
        });
        const task = await taskRes.json();
        return { workspaceId: task.workspaceId, taskId: task.id };
    }""")
    return result


def setup(page, base_url, workspace_id, task_id):
    page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
    page.wait_for_load_state("networkidle")
    time.sleep(5)

    # Create a second task so we have two tabs to switch between
    second = _create_second_task(page, base_url)
    if second:
        page.goto(f"{base_url}/#/ws/{second['workspaceId']}/agent/{second['taskId']}")
        page.wait_for_load_state("networkidle")
        time.sleep(3)
        # Navigate back to the first workspace
        page.goto(f"{base_url}/#/ws/{workspace_id}/agent/{task_id}")
        page.wait_for_load_state("networkidle")
        time.sleep(2)


def action(page):
    # Find workspace tab buttons in the WorkspaceTabs area
    # Try several selectors since the tab bar implementation may vary
    tabs = page.locator('[data-testid="workspace-tab"]').all()

    if len(tabs) < 2:
        # Fall back to any tab-like elements in the top bar
        tabs = page.locator('[role="tab"]').all()

    if len(tabs) < 2:
        # Try clicking the "+" new workspace button path indirectly — just navigate
        # directly via URL to simulate a tab switch
        result = page.evaluate("""async () => {
            const res = await fetch('/api/v1/projects');
            const projects = await res.json();
            const projectId = projects[0]?.objectId;
            const wsRes = await fetch(`/api/v1/projects/${projectId}/workspaces`);
            const workspaces = await wsRes.json();
            return workspaces.map(ws => ({ id: ws.objectId }));
        }""")
        if result and len(result) >= 2:
            ws_id_2 = result[1]["id"]
            # Simulate tab switch via navigation
            page.evaluate(f"window.location.hash = '#/ws/{ws_id_2}'")
            time.sleep(0.5)
            # Navigate back
            page.go_back()
            time.sleep(0.5)
        return

    # Click second tab
    tabs[1].click()
    time.sleep(0.4)

    # Click first tab
    tabs[0].click()
    time.sleep(0.4)

    # Click second tab again
    tabs[1].click()
    time.sleep(0.4)
