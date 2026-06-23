"""Integration tests for the CI Babysitter feature.

Each test installs a fake ``gh`` CLI that returns a controlled PR
state (failed checks, merged, etc.) and asserts that
``CIBabysitterCoordinator`` reacts correctly: a "CI Babysitter" agent
tab is spawned, the configured prompt is delivered, the agent is
retired on merge, and pause prevents prompts.

The classifier's first-poll baseline behavior (architecture's "Risks
and Mitigations" section) requires PIPELINE_FAILED to fire only on a
*change* into the failed state, not on the very first poll. Tests
therefore start with a non-failed check state (the baseline), confirm
the poller actually observed it, and then flip the checks to failed to
trigger an actionable transition. That arming sequence is encapsulated
in `_arm_failed_transition`.
"""

import stat
import textwrap
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.pr_popover import PlaywrightPrPopoverElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# A registered terminal program that opts into automated prompts: it signals
# idle (reaches its prompt), then echoes each received line as RECEIVED:<line>
# and goes busy — letting the babysitter's readiness wait + guarded write be
# observed in the terminal buffer. Copied from
# test_terminal_agent_automated_prompts.py (the canonical fake program).
_FAKE_PROMPTS_COMMAND = (
    "echo FAKE-PROMPTS-BANNER; sculpt signal idle; printf %sDONE IDLE-; echo; "
    + "while read -r _line; do echo RECEIVED:$_line; sculpt signal busy; done"
)
# Fragment of the proactive MRU-non-driveable disabled reason (see
# _DISABLED_REASON_MRU_NON_DRIVEABLE in the coordinator).
_NON_DRIVEABLE_REASON_FRAGMENT = "terminal that can't receive automated prompts"


def _write_registration(
    instance: SculptorInstance, registration_id: str, display_name: str, *, accepts_automated_prompts: bool
) -> Path:
    """Write a terminal-agent registration TOML and return its path (for cleanup)."""
    registrations_dir = instance.sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    path = registrations_dir / f"{registration_id}.toml"
    opt_in_line = "accepts_automated_prompts = true\n" if accepts_automated_prompts else ""
    path.write_text(f'display_name = "{display_name}"\nlaunch_command = "{_FAKE_PROMPTS_COMMAND}"\n{opt_in_line}')
    return path


_MERGED_MODE_STABLE_WAIT_MS = 25_000
# Time to wait between baseline-recording poll and the next state-changing
# poll. The polling service uses a 10s minimum interval in tests; 12s is a
# safe lower bound that still keeps the test snappy.
_BASELINE_POLL_SETTLE_MS = 12_000

_FAKE_GITHUB_REMOTE = "https://github.com/test-org/test-repo.git"

# Shared fake gh script driven by a `state_file` (mode). The backend issues a
# single `gh api graphql` query for PR status (see pr_status.py), so each mode
# emits that GraphQL response envelope.
#   mode = running  → PR is open with a pending (running) check rollup.
#   mode = failed   → PR is open with a failed check rollup.
#   mode = merged   → PR is merged.
#   mode = closed   → PR is closed without merging.
# The mode-file path is injected via ``.replace("{state_file}", ...)`` (not
# ``.format``) so the JSON braces below don't need escaping.
_FAKE_GH_STATE_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{state_file}")
case "$MODE" in
    running)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":7,"title":"Test PR","url":"https://github.com/test/repo/pull/7","state":"OPEN","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":{"state":"PENDING"}}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
        ;;
    failed)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":7,"title":"Test PR","url":"https://github.com/test/repo/pull/7","state":"OPEN","baseRefName":"main","commits":{"nodes":[{"commit":{"statusCheckRollup":{"state":"FAILURE"}}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
        ;;
    merged)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":7,"title":"Test PR","url":"https://github.com/test/repo/pull/7","state":"MERGED","baseRefName":"main","commits":{"nodes":[]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
        ;;
    *)
        echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
        ;;
esac
"""


def _install_fake_gh(fake_bin_dir: Path, script: str) -> None:
    script_path = fake_bin_dir / "gh"
    script_path.write_text(textwrap.dedent(script))
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)


# Fake `gh` returning one OPEN PR that GitHub reports as CONFLICTING. The
# backend issues a single `gh api graphql` query; this node carries
# "mergeable":"CONFLICTING", so a backend that surfaces PR merge conflicts maps
# it to has_conflicts=True and the babysitter fires on the very first poll (a
# merge conflict needs no baseline change, unlike a pipeline failure -- see
# transitions.classify_transitions). A backend that ignores the mergeable field
# (the SCU-1529 bug) leaves has_conflicts=None and no babysitter tab appears.
_FAKE_GH_CONFLICTING_PR_SCRIPT = """\
#!/bin/bash
if [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[{"number":42,"title":"Test PR","url":"https://github.com/test/repo/pull/42","state":"OPEN","baseRefName":"main","mergeable":"CONFLICTING","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]}}}}'
fi
"""


def _install_state_driven_gh(instance: SculptorInstance, state_file: Path) -> None:
    _install_fake_gh(
        instance.fake_bin_dir,
        _FAKE_GH_STATE_SCRIPT.replace("{state_file}", str(state_file)),
    )


def _set_remote(instance: SculptorInstance, url: str) -> None:
    repo = instance.repo
    try:
        repo.repo.run_git(("remote", "remove", "origin"))
    except Exception:
        pass
    repo.repo.run_git(("remote", "add", "origin", url))
    full_spa_reload(instance.page)


_CONFIG_API_TIMEOUT_MS = 30_000


def _enable_babysitter(instance: SculptorInstance) -> None:
    """Enable the CI Babysitter via the user-config API.

    Also sets default_llm to FAKE_CLAUDE so the coordinator-spawned babysitter
    agent uses the deterministic test model. The babysitter normally inherits
    its model from the workspace's most recent agent, but the polling cycle
    can fire before the parent agent's first chat message is committed, so
    we set the user-config fallback explicitly here.
    """
    base_url = instance.backend_api_url.rstrip("/")
    response = instance.page.request.get(f"{base_url}/api/v1/config", timeout=_CONFIG_API_TIMEOUT_MS)
    assert response.ok, f"GET /api/v1/config failed: {response.status}"
    config = response.json()
    babysitter = dict(config.get("ciBabysitter") or {})
    babysitter["enabled"] = True
    config["ciBabysitter"] = babysitter
    config["defaultLlm"] = "FAKE_CLAUDE"
    put_response = instance.page.request.put(
        f"{base_url}/api/v1/config",
        data={"userConfig": config},
        timeout=_CONFIG_API_TIMEOUT_MS,
    )
    assert put_response.ok, f"PUT /api/v1/config failed: {put_response.status}"


_PIPELINE_PROMPT_FRAGMENT = "Investigate the failing pipeline for this PR"

# Fragment of the default merge-conflict prompt (user_config.CIBabysitterConfig).
# Chosen to be provider-neutral so the assertion survives the "MR"/"PR" wording.
_MERGE_CONFLICT_PROMPT_FRAGMENT = "merge conflict with its base branch"


def _arm_failed_transition(instance: SculptorInstance, state_file: Path) -> None:
    """Flip checks running → failed, confirming the poller actually observed the
    non-failed baseline (via the PR popover "Running" badge) before the flip.

    The classifier suppresses PIPELINE_FAILED on the first poll (prev is None) so
    a Sculptor restart against an already-red PR doesn't burn a retry. A
    non-failed → failed transition therefore only fires if a non-failed poll
    landed first. A fixed wall-clock window can't guarantee that under CI load —
    and after a backend restart the coordinator's in-memory prev_status resets to
    None and polling resumes lazily, so the window can elapse before any
    non-failed poll lands. Waiting on the badge — driven by the same poll result
    the coordinator consumes — guarantees prev_status is non-failed before we
    write "failed", regardless of timing or restart state.
    """
    state_file.write_text("running")
    pr_popover = PlaywrightPrPopoverElement(instance.page)
    chevron = pr_popover.get_chevron()
    expect(chevron).to_be_visible(timeout=60_000)
    chevron.click()
    expect(pr_popover.get_pipeline_status_badge()).to_have_text("Running", timeout=60_000)
    instance.page.keyboard.press("Escape")
    state_file.write_text("failed")


@user_story("to have Sculptor's CI Babysitter automatically investigate a failed pipeline")
def test_scenario_1_failed_pipeline_creates_babysitter(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """When CI fails on a PR opened from a workspace, the coordinator spawns
    a 'CI Babysitter' agent tab and delivers the configured prompt verbatim.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("running")

    _enable_babysitter(sculptor_instance_)
    _install_state_driven_gh(sculptor_instance_, state_file)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _arm_failed_transition(sculptor_instance_, state_file)

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)

    babysitter_tab.first.click()
    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompt_messages = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompt_messages.first).to_be_visible()


@user_story("to retain babysitter history after the PR is merged, with no further automated prompts")
def test_scenario_7_merged_pr_retires_babysitter(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Once a PR is merged, the coordinator stops sending prompts but
    the babysitter task and its conversation history remain.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("running")

    _install_state_driven_gh(sculptor_instance_, state_file)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)
    _enable_babysitter(sculptor_instance_)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _arm_failed_transition(sculptor_instance_, state_file)

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)
    babysitter_tab.first.click()

    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompts).to_have_count(1)

    state_file.write_text("merged")
    sculptor_instance_.page.wait_for_timeout(_MERGED_MODE_STABLE_WAIT_MS)
    expect(pipeline_prompts).to_have_count(1)

    expect(babysitter_tab.first).to_be_visible()


@user_story("to silence the CI Babysitter for a PR while still seeing the babysitter tab")
def test_scenario_4_pause_toggle_prevents_prompt(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Toggling pause in the PR popover stops the coordinator from sending
    further prompts to the babysitter for this PR. Unpausing resumes
    listening but does not retro-fire for the existing red state.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("running")

    _install_state_driven_gh(sculptor_instance_, state_file)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)
    _enable_babysitter(sculptor_instance_)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _arm_failed_transition(sculptor_instance_, state_file)

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)

    pr_popover = PlaywrightPrPopoverElement(sculptor_instance_.page)
    pr_chevron = pr_popover.get_chevron()
    expect(pr_chevron).to_be_visible(timeout=60_000)
    pr_chevron.click()

    pause_toggle = pr_popover.get_babysitter_pause_toggle()
    expect(pause_toggle).to_be_visible()
    pause_toggle.click()
    sculptor_instance_.page.keyboard.press("Escape")

    babysitter_tab.first.click()
    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompts).to_have_count(1)

    # Re-arm the failed edge (running → failed again) while paused; the pause
    # must suppress a second prompt. The badge-confirmed arm guarantees the
    # non-failed baseline is observed, so a missed prompt here means pause
    # worked, not that the transition never armed.
    _arm_failed_transition(sculptor_instance_, state_file)
    sculptor_instance_.page.wait_for_timeout(_MERGED_MODE_STABLE_WAIT_MS)
    expect(pipeline_prompts).to_have_count(1)


@user_story("to keep the CI Babysitter paused for a workspace across a backend restart")
def test_pause_state_persists_across_restart(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """Pausing the CI Babysitter for a workspace must survive a backend restart.

    The per-workspace paused flag is set from the PR popover. Before the fix it
    lived only in ``CIBabysitterCoordinator._state`` (in-memory), so a restart
    dropped it and the workspace reverted to "Active". This test pauses in one
    backend, restarts onto the same database, and asserts the popover still
    reports "Paused".
    """
    state_file = tmp_path / "glab_state"
    pipeline_id_file = tmp_path / "pipeline_id"
    state_file.write_text("failed")
    pipeline_id_file.write_text("100")

    # First backend: pause the babysitter for the workspace via the PR popover.
    with sculptor_instance_factory_.spawn_instance() as instance:
        _install_state_driven_glab(instance, state_file, pipeline_id_file)
        _set_remote(instance, _FAKE_GITLAB_REMOTE)
        _enable_babysitter(instance)

        start_task_and_wait_for_ready(instance.page, "say hello")

        pr_popover = PlaywrightPrPopoverElement(instance.page)
        pr_chevron = pr_popover.get_chevron()
        expect(pr_chevron).to_be_visible(timeout=60_000)
        pr_chevron.click()

        pause_toggle = pr_popover.get_babysitter_pause_toggle()
        expect(pause_toggle).to_be_visible()
        babysitter_status = pr_popover.get_babysitter_status()
        # Starts Active (not paused); flip it to Paused.
        expect(babysitter_status).to_have_text("Active")
        pause_toggle.click()
        expect(babysitter_status).to_have_text("Paused")
        instance.page.keyboard.press("Escape")

    # Second backend on the same database: the paused flag must be restored.
    with sculptor_instance_factory_.spawn_instance() as instance:
        _install_state_driven_glab(instance, state_file, pipeline_id_file)
        _set_remote(instance, _FAKE_GITLAB_REMOTE)
        _enable_babysitter(instance)

        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        pr_popover = PlaywrightPrPopoverElement(instance.page)
        pr_chevron = pr_popover.get_chevron()
        expect(pr_chevron).to_be_visible(timeout=60_000)
        pr_chevron.click()

        babysitter_status = pr_popover.get_babysitter_status()
        # Before the fix this read "Active" — the paused flag was lost on restart.
        expect(babysitter_status).to_have_text("Paused")
        expect(pr_popover.get_babysitter_pause_toggle()).not_to_be_checked()


@user_story("to have the CI Babysitter drive my terminal agent to fix a failed pipeline")
def test_babysitter_drives_registered_terminal_agent(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """When the workspace's most-recent agent is a registered, opt-in terminal
    agent, the babysitter spawns its OWN terminal task on CI failure, waits for
    the program to reach its prompt, and writes the fix-CI prompt to its PTY.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("running")

    registration = _write_registration(
        sculptor_instance_, "babysit-prompts", "Babysit Prompts", accepts_automated_prompts=True
    )
    try:
        _enable_babysitter(sculptor_instance_)
        _install_state_driven_gh(sculptor_instance_, state_file)
        _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

        page = sculptor_instance_.page
        start_task_and_wait_for_ready(page, "say hello")

        # Make the registered terminal agent the workspace's most-recent agent.
        agent_tabs = PlaywrightAgentTabBarElement(page)
        agent_tabs.open_agent_type_menu()
        registered_item = agent_tabs.get_agent_type_menu_item_registered("babysit-prompts")
        expect(registered_item).to_be_visible()
        registered_item.click()
        user_tab = agent_tabs.get_agent_tab_by_name("Babysit Prompts 1").first
        expect(user_tab).to_be_visible()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        wait_for_xterm_substring(page, "IDLE-DONE")  # the program is at its prompt

        _arm_failed_transition(sculptor_instance_, state_file)

        # The babysitter spawns its own "CI Babysitter" terminal task (distinct
        # from the user's tab) and writes the fix-CI prompt to its PTY.
        babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
        expect(babysitter_tab.first).to_be_visible(timeout=60_000)
        babysitter_tab.first.click()
        expect(get_agent_terminal_panel(page)).to_be_visible()
        wait_for_xterm_substring(page, "RECEIVED:Investigate the failing pipeline")
    finally:
        registration.unlink(missing_ok=True)


@user_story("to understand why the CI Babysitter can't act when my agent is a plain terminal")
def test_plain_terminal_mru_shows_disabled_reason(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """When the workspace's most-recent agent is a plain terminal (not driveable),
    the PR popover proactively shows the disabled reason and the pause toggle is
    inert — without needing a pipeline failure first.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("failed")

    _enable_babysitter(sculptor_instance_)
    _install_state_driven_gh(sculptor_instance_, state_file)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, "say hello")

    # Make the workspace's most-recent agent a plain terminal (never driveable).
    agent_tabs = PlaywrightAgentTabBarElement(page)
    agent_tabs.open_agent_type_menu()
    agent_tabs.get_agent_type_menu_item_terminal().click()
    terminal_tab = agent_tabs.get_agent_tab_by_name("Terminal 1").first
    expect(terminal_tab).to_be_visible()

    # Let the polling create per-workspace state so the proactive reason is
    # computed before the popover fetches it.
    page.wait_for_timeout(_BASELINE_POLL_SETTLE_MS)

    pr_popover = PlaywrightPrPopoverElement(page)
    pr_chevron = pr_popover.get_chevron()
    expect(pr_chevron).to_be_visible(timeout=60_000)
    pr_chevron.click()

    expect(pr_popover.get_babysitter_status()).to_contain_text(_NON_DRIVEABLE_REASON_FRAGMENT, timeout=30_000)
    # A persistent reason makes the toggle inert (it won't act regardless of pause).
    expect(pr_popover.get_babysitter_pause_toggle()).to_be_disabled()


@user_story("to pick which agent the CI Babysitter uses, limited to ones that accept automated prompts")
def test_settings_selector_lists_only_driveable_harnesses(sculptor_instance_: SculptorInstance) -> None:
    """The 'Babysitter agent' selector lists MRU + Claude + opt-in registered
    terminal agents, and excludes non-opt-in registrations and plain terminals.
    """
    opt_in = _write_registration(sculptor_instance_, "agent-opt-in", "Opt In Agent", accepts_automated_prompts=True)
    no_opt_in = _write_registration(
        sculptor_instance_, "agent-no-opt-in", "No Opt In Agent", accepts_automated_prompts=False
    )
    try:
        page = sculptor_instance_.page
        settings_page = navigate_to_settings_page(page=page)
        ci_section = settings_page.click_on_ci()
        ci_section.enable()
        ci_section.open_agent_select()

        expect(ci_section.get_agent_option("Most recently used")).to_be_visible()
        expect(ci_section.get_agent_option("Claude")).to_be_visible()
        expect(ci_section.get_agent_option("Opt In Agent")).to_be_visible()
        # Non-opt-in registration and plain terminals are never selectable.
        expect(ci_section.get_agent_option("No Opt In Agent")).to_have_count(0)
        expect(ci_section.get_agent_option("Terminal")).to_have_count(0)
    finally:
        opt_in.unlink(missing_ok=True)
        no_opt_in.unlink(missing_ok=True)


@user_story("to keep a single CI Babysitter tab across restarts instead of a duplicate")
def test_restart_reuses_existing_babysitter_tab(
    sculptor_instance_factory_: SculptorInstanceFactory, tmp_path: Path
) -> None:
    """A CI failure after a backend restart reuses the existing 'CI Babysitter'
    tab instead of spawning a duplicate.

    Regression for SCU-1530. The coordinator tracked the babysitter task id
    only in memory, so after a restart it no longer knew a babysitter task
    already existed for the workspace and created a second one — leaving two
    'CI Babysitter' tabs. The fix re-adopts the persisted babysitter task, so a
    post-restart failure delivers its prompt to the existing tab.
    """
    state_file = tmp_path / "gh_state"
    state_file.write_text("running")

    # First launch: a failed pipeline spawns the one-and-only babysitter tab and
    # delivers the configured prompt to it.
    with sculptor_instance_factory_.spawn_instance() as instance:
        _enable_babysitter(instance)
        _install_state_driven_gh(instance, state_file)
        _set_remote(instance, _FAKE_GITHUB_REMOTE)

        start_task_and_wait_for_ready(instance.page, "say hello")
        _arm_failed_transition(instance, state_file)

        agent_tabs = PlaywrightAgentTabBarElement(instance.page)
        babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
        expect(babysitter_tab).to_have_count(1, timeout=60_000)
        babysitter_tab.first.click()
        alpha_chat = get_alpha_chat_view(instance.page)
        pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
        expect(pipeline_prompts).to_have_count(1)

    # Restart against the same database, then drive another CI failure. The
    # coordinator's in-memory babysitter_task_id is gone after the restart, so
    # it must re-discover the persisted babysitter task rather than create a new
    # one.
    with sculptor_instance_factory_.spawn_instance() as instance:
        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        agent_tabs = PlaywrightAgentTabBarElement(instance.page)
        babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
        expect(babysitter_tab).to_have_count(1)
        babysitter_tab.first.click()
        alpha_chat = get_alpha_chat_view(instance.page)
        pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
        expect(pipeline_prompts).to_have_count(1)

        # Re-establish a non-failed post-restart baseline, confirm the poller
        # observed it, then flip back to failed so a fresh PIPELINE_FAILED
        # transition fires. With the fix this is delivered to the existing
        # babysitter tab (its prompt count goes to 2) and there is still exactly
        # one tab. With the bug a duplicate 'CI Babysitter' tab is created
        # instead.
        _arm_failed_transition(instance, state_file)

        expect(pipeline_prompts).to_have_count(2, timeout=60_000)
        expect(agent_tabs.get_agent_tab_by_name("CI Babysitter")).to_have_count(1)


@user_story("to have the CI Babysitter automatically resolve a merge conflict on a GitHub PR")
def test_github_pr_merge_conflict_creates_babysitter(sculptor_instance_: SculptorInstance) -> None:
    """When a GitHub PR opened from a workspace has a merge conflict, the
    coordinator spawns a 'CI Babysitter' agent tab and delivers the configured
    merge-conflict prompt.

    Regression for SCU-1529: the GitHub PR status path never surfaced
    has_conflicts (the `gh api graphql` query didn't request `mergeable`, and
    the parser didn't map it), so the coordinator's MERGE_CONFLICT transition
    never fired for PRs and no babysitter tab ever appeared. A merge conflict
    surfaces on the first poll, so -- unlike the pipeline-failure scenarios --
    no baseline bump is needed.
    """
    _enable_babysitter(sculptor_instance_)
    _install_fake_gh(sculptor_instance_.fake_bin_dir, _FAKE_GH_CONFLICTING_PR_SCRIPT)
    _set_remote(sculptor_instance_, _FAKE_GITHUB_REMOTE)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)

    babysitter_tab.first.click()
    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    conflict_prompt_messages = alpha_chat.get_messages().filter(has_text=_MERGE_CONFLICT_PROMPT_FRAGMENT)
    expect(conflict_prompt_messages.first).to_be_visible()
