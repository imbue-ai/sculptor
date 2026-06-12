"""End-to-end regression test for SCU-1302.

Claude Code parses skills leniently: a ``SKILL.md`` with no YAML frontmatter
is still discovered, using its directory name as the skill name. Sculptor used
to reject such skills outright, so a personal skill like ``openhost-zack``
(whose ``SKILL.md`` is just a plain-text body) was silently dropped and the
SkillsPanel showed "No matching skills".

This test pins the desired, Claude-matching behavior: a frontmatter-less
``SKILL.md`` must still surface as a chip in the SkillsPanel.
"""

import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _create_skill_without_frontmatter(project_path: Path, skill_name: str, body: str) -> None:
    """Create a committed skill whose SKILL.md has no YAML frontmatter.

    The skill must be committed so CLONE-mode workspaces include it in the
    clone. Unlike a well-formed skill, the SKILL.md here is a bare body with
    no leading ``---`` block — exactly the shape Claude Code accepts but
    Sculptor historically rejected (SCU-1302).
    """
    skill_dir = project_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body)
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Add frontmatter-less skill {skill_name}"],
        cwd=project_path,
        check=True,
    )


@user_story("to use a personal skill whose SKILL.md has no YAML frontmatter, just like Claude Code")
def test_skills_panel_lists_skill_without_frontmatter(sculptor_instance_: SculptorInstance) -> None:
    """A SKILL.md missing YAML frontmatter must still appear in the SkillsPanel.

    Mirrors the user's reported ``openhost-zack`` skill: a SKILL.md whose first
    line is plain prose rather than a ``---`` frontmatter block. The chip is
    named after the skill's directory (there is no frontmatter ``name`` to read).
    """
    skill_name = "openhost-no-frontmatter"
    _create_skill_without_frontmatter(
        sculptor_instance_.project_path,
        skill_name,
        "openhost is a cloud platform for self-hosting apps.\n",
    )

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        prompt='fake_claude:text `{"text": "Ready"}`',
    )

    skills_panel = task_page.open_skills_panel()

    expect(skills_panel.get_skill_chip(skill_name)).to_be_visible()
