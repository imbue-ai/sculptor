"""Scenario: Workspace switching render cascade.

Measures re-renders when the user clicks between workspace rows in the
sidebar. Switching navigates to a different workspace URL and changes the
active agent, causing WorkspacePage to mount new content.

This tests whether workspace switching causes excessive re-renders in
components that should be stable across switches (the workspace sidebar,
the section-grid structure).
"""

import time

DESCRIPTION = "Workspace switching (sidebar rows)"

# Memo-wrapped exports (e.g. SplittableSection) are recorded under their inner
# function names ("SplittableSectionComponent").
TARGET_COMPONENTS = [
    "WorkspacePage",
    "WorkspacePageContent",
    "WorkspaceLayoutShell",
    "WorkspaceSidebar",
    "WorkspaceHeaderComponent",
    "SectionGrid",
    "SplittableSectionComponent",
    "PanelSectionComponent",
    "SectionHeaderComponent",
    "SectionBodyComponent",
    "AlphaChatInterface",
    "ChatPanelContent",
    "ChatInput",
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
    # Find the workspace rows in the sidebar
    rows = page.locator('[data-testid="SIDEBAR_WORKSPACE_ROW"]').all()

    if len(rows) < 2:
        # Fall back to navigating directly via URL to simulate a workspace switch
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
            # Simulate a workspace switch via navigation
            page.evaluate(f"window.location.hash = '#/ws/{ws_id_2}'")
            time.sleep(0.5)
            # Navigate back
            page.go_back()
            time.sleep(0.5)
        return

    # Click second workspace row
    rows[1].click()
    time.sleep(0.4)

    # Click first workspace row
    rows[0].click()
    time.sleep(0.4)

    # Click second workspace row again
    rows[1].click()
    time.sleep(0.4)
