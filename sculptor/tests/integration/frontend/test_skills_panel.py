"""End-to-end tests for the SkillsPanel side panel.

The complementary `/`-trigger autocomplete flow is covered by
``test_skill_autocomplete.py`` and ``test_pseudo_skills.py``; these tests
pin the SkillsPanel UI itself: opening the panel, the chip list, click-to-
insert into the editor, and the search filter.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_skill_in_directory(project_path: Path, skill_name: str, description: str) -> None:
    """Create a committed skill in the project's .claude/skills/ directory.

    The skill must be committed so CLONE-mode workspaces include it in the clone.
    """
    skill_dir = project_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name}\ndescription: {description}\n---\nSkill instructions.\n"
    )
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add skill {skill_name}"],
        cwd=project_path,
        check=True,
    )


@user_story("to browse skills available in the workspace from a side panel")
def test_skills_panel_lists_workspace_skill(sculptor_instance_: SculptorInstance) -> None:
    """The SkillsPanel must list custom skills committed to .claude/skills/."""
    skill_name = "skills-panel-custom"
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        skill_name,
        "Skill for SkillsPanel listing test",
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    skills_panel = task_page.open_skills_panel()

    expect(skills_panel.get_skill_chip(skill_name)).to_be_visible()


@user_story("to insert a /skill into the chat by clicking it in the SkillsPanel")
def test_skills_panel_click_inserts_mention_chip(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a skill in the SkillsPanel inserts a mention chip into the editor."""
    skill_name = "skills-panel-insert"
    _create_skill_in_directory(
        sculptor_instance_.project_path,
        skill_name,
        "Skill for SkillsPanel click-to-insert test",
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()

    expect(chat_panel.get_mention_spans()).not_to_be_visible()

    skills_panel = task_page.open_skills_panel()
    chip = skills_panel.get_skill_chip(skill_name)
    expect(chip).to_be_visible()
    chip.click()

    # After the click, the editor should contain a mention chip with the
    # skill name. This proves the SkillsPanel → chatActionsAtom →
    # editor.insertContent pipeline is wired up.
    mention_spans = chat_panel.get_mention_spans()
    expect(mention_spans).to_be_visible()
    expect(mention_spans).to_contain_text(skill_name)


@user_story("to insert the top search match by pressing Enter")
def test_skills_panel_keyboard_navigation_inserts_chip(sculptor_instance_: SculptorInstance) -> None:
    """Search → ArrowDown → Enter must insert the second filtered skill.

    Pins the keyboard-navigation contract: opening search auto-selects the
    first chip, ArrowDown advances the selection, and Enter inserts whatever
    chip is currently selected.
    """
    first = "skill-keyboard-alpha"
    second = "skill-keyboard-beta"
    _create_skill_in_directory(sculptor_instance_.project_path, first, "Alpha skill")
    _create_skill_in_directory(sculptor_instance_.project_path, second, "Beta skill")

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_mention_spans()).not_to_be_visible()

    skills_panel = task_page.open_skills_panel()
    expect(skills_panel.get_skill_chip(first)).to_be_visible()
    expect(skills_panel.get_skill_chip(second)).to_be_visible()

    # Filter to just the two `skill-keyboard-*` skills so neighbouring rows
    # don't influence the first/second selection — there can be unrelated
    # skills (built-ins, plugin skills) above ours alphabetically.
    search_input = skills_panel.open_search()
    search_input.fill("skill-keyboard")

    # First chip should be selected on entry to search mode (and stays
    # selected as we type, because typing resets the selection to index 0).
    alpha_chip = skills_panel.get_skill_chip(first)
    expect(alpha_chip).to_have_attribute("data-selected", "true")

    search_input.press("ArrowDown")
    beta_chip = skills_panel.get_skill_chip(second)
    expect(beta_chip).to_have_attribute("data-selected", "true")
    search_input.press("Enter")

    mention_spans = chat_panel.get_mention_spans()
    expect(mention_spans).to_be_visible()
    expect(mention_spans).to_contain_text(second)


@user_story("to filter the SkillsPanel list by typing into the search box")
def test_skills_panel_search_filters_list(sculptor_instance_: SculptorInstance) -> None:
    """Typing into the SkillsPanel search input filters the visible chips."""
    keep = "skill-search-keep"
    drop = "skill-search-drop"
    _create_skill_in_directory(sculptor_instance_.project_path, keep, "Keeps me on screen")
    _create_skill_in_directory(sculptor_instance_.project_path, drop, "Drops out of search")

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    skills_panel = task_page.open_skills_panel()

    expect(skills_panel.get_skill_chip(keep)).to_be_visible()
    expect(skills_panel.get_skill_chip(drop)).to_be_visible()

    # Open the search input and filter to a substring that only matches `keep`.
    search_input = skills_panel.open_search()
    search_input.fill("keep")

    expect(skills_panel.get_skill_chip(keep)).to_be_visible()
    expect(skills_panel.get_skill_chip(drop)).not_to_be_visible()
