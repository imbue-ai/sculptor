"""Unit tests for skill and command discovery logic.

Tests the pure functions in sculptor.web.skills that scan for skills
(directory-based with SKILL.md) and commands (flat markdown files)
from both repo and home directory paths.
"""

from pathlib import Path

import pytest

from sculptor.web.data_types import SkillInfo
from sculptor.web.skills import SkillSourceKind
from sculptor.web.skills import _parse_skill_frontmatter
from sculptor.web.skills import _scan_commands_directory
from sculptor.web.skills import _scan_skills_directory
from sculptor.web.skills import discover_skills
from sculptor.web.skills import get_skill_source_directories
from sculptor.web.skills import parse_command_frontmatter


def test_parse_skill_frontmatter_extracts_name_and_description() -> None:
    content = "---\nname: fix-bug\ndescription: Fix a bug using TDD\n---\nBody content\n"
    name, description = _parse_skill_frontmatter(content)
    assert name == "fix-bug"
    assert description == "Fix a bug using TDD"


def test_parse_skill_frontmatter_strips_multiline_description() -> None:
    content = "---\nname: review-goals\ndescription: |\n  Review a goals document\n  for completeness.\n---\nBody\n"
    name, description = _parse_skill_frontmatter(content)
    assert name == "review-goals"
    assert description == "Review a goals document\nfor completeness."


def test_parse_skill_frontmatter_returns_none_without_frontmatter() -> None:
    content = "No frontmatter here\n"
    name, description = _parse_skill_frontmatter(content)
    assert name is None
    assert description is None


def test_parse_skill_frontmatter_returns_none_for_unclosed_frontmatter() -> None:
    content = "---\nname: broken\n"
    name, description = _parse_skill_frontmatter(content)
    assert name is None
    assert description is None


def test_parse_skill_frontmatter_returns_none_for_invalid_yaml() -> None:
    content = "---\n: invalid: yaml: [[\n---\n"
    name, description = _parse_skill_frontmatter(content)
    assert name is None
    assert description is None


def test_parse_skill_frontmatter_returns_none_for_non_dict_yaml() -> None:
    content = "---\n- just a list\n---\n"
    name, description = _parse_skill_frontmatter(content)
    assert name is None
    assert description is None


def test_parse_skill_frontmatter_returns_name_with_none_description() -> None:
    content = "---\nname: no-desc\n---\nBody\n"
    name, description = _parse_skill_frontmatter(content)
    assert name == "no-desc"
    assert description is None


def test_parse_skill_frontmatter_rejects_non_str_name() -> None:
    content = "---\nname: 42\ndescription: A skill\n---\n"
    name, description = _parse_skill_frontmatter(content)
    assert name is None
    assert description is None


def test_parse_skill_frontmatter_drops_non_str_description() -> None:
    content = "---\nname: ok\ndescription: 42\n---\n"
    name, description = _parse_skill_frontmatter(content)
    assert name == "ok"
    assert description is None


def test_parse_command_frontmatter_extracts_description() -> None:
    content = "---\ndescription: Identify style issues\n---\nBody content\n"
    description = parse_command_frontmatter(content)
    assert description == "Identify style issues"


def test_parse_command_frontmatter_strips_multiline_description() -> None:
    content = "---\ndescription: |\n  Fix ratchet violations\n  in the codebase.\n---\nBody\n"
    description = parse_command_frontmatter(content)
    assert description == "Fix ratchet violations\nin the codebase."


def test_parse_command_frontmatter_returns_none_without_frontmatter() -> None:
    content = "Just a markdown file\n"
    description = parse_command_frontmatter(content)
    assert description is None


def test_parse_command_frontmatter_returns_none_without_description() -> None:
    content = "---\nargument-hint: <file>\n---\nBody\n"
    description = parse_command_frontmatter(content)
    assert description is None


def test_parse_command_frontmatter_returns_none_for_invalid_yaml() -> None:
    content = "---\n: bad: yaml: [[\n---\n"
    description = parse_command_frontmatter(content)
    assert description is None


def test_parse_command_frontmatter_returns_none_for_non_dict_yaml() -> None:
    content = "---\n- a list\n---\n"
    description = parse_command_frontmatter(content)
    assert description is None


def test_scan_skills_directory_finds_valid_skills(tmp_path: Path) -> None:
    skills_dir = tmp_path / ".claude" / "skills"
    skill_a = skills_dir / "alpha"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha skill\n---\nContent\n")

    skill_b = skills_dir / "beta"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text("---\nname: beta\ndescription: Beta skill\n---\nContent\n")

    result = _scan_skills_directory(skills_dir)
    assert result == [
        SkillInfo(name="alpha", description="Alpha skill", source="custom", file_path=str(skill_a / "SKILL.md")),
        SkillInfo(name="beta", description="Beta skill", source="custom", file_path=str(skill_b / "SKILL.md")),
    ]


def test_scan_skills_directory_uses_dir_name_when_frontmatter_missing(tmp_path: Path) -> None:
    """A SKILL.md without frontmatter is kept, named after its directory (SCU-1302).

    Claude Code parses skills leniently; Sculptor must match by falling back to
    the directory name rather than dropping the skill. Mirrors the reported
    ``openhost-zack`` skill whose SKILL.md is just a plain-text body.
    """
    skills_dir = tmp_path / ".claude" / "skills"
    good_skill = skills_dir / "good"
    good_skill.mkdir(parents=True)
    (good_skill / "SKILL.md").write_text("---\nname: good\ndescription: A good skill\n---\n")

    no_frontmatter_skill = skills_dir / "openhost-zack"
    no_frontmatter_skill.mkdir()
    (no_frontmatter_skill / "SKILL.md").write_text("openhost is a cloud platform for self-hosting apps.\n")

    result = _scan_skills_directory(skills_dir)
    assert result == [
        SkillInfo(
            name="good",
            description="A good skill",
            source="custom",
            file_path=str(good_skill / "SKILL.md"),
        ),
        SkillInfo(
            name="openhost-zack",
            description="",
            source="custom",
            file_path=str(no_frontmatter_skill / "SKILL.md"),
        ),
    ]


def test_scan_skills_directory_uses_dir_name_when_frontmatter_malformed(tmp_path: Path) -> None:
    """A SKILL.md whose frontmatter is malformed still surfaces, named after its directory.

    The directory name is always a valid fallback identity, so broken YAML or a
    non-string ``name`` should not make the skill disappear entirely.
    """
    skills_dir = tmp_path / ".claude" / "skills"
    skill = skills_dir / "broken-yaml"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\n: invalid: yaml: [[\n---\nBody\n")

    result = _scan_skills_directory(skills_dir)
    assert result == [
        SkillInfo(name="broken-yaml", description="", source="custom", file_path=str(skill / "SKILL.md")),
    ]


def test_scan_skills_directory_skips_directories_without_skill_md(tmp_path: Path) -> None:
    skills_dir = tmp_path / ".claude" / "skills"
    skill = skills_dir / "no-md"
    skill.mkdir(parents=True)
    (skill / "README.md").write_text("Not a SKILL.md\n")

    result = _scan_skills_directory(skills_dir)
    assert result == []


def test_scan_skills_directory_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    result = _scan_skills_directory(tmp_path / "nonexistent")
    assert result == []


def test_scan_skills_directory_uses_empty_description_when_missing(tmp_path: Path) -> None:
    skills_dir = tmp_path / ".claude" / "skills"
    skill = skills_dir / "no-desc"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: no-desc\n---\nBody\n")

    result = _scan_skills_directory(skills_dir)
    assert result == [SkillInfo(name="no-desc", description="", source="custom", file_path=str(skill / "SKILL.md"))]


def test_scan_commands_directory_finds_markdown_commands(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "fix-style.md").write_text("---\ndescription: Fix style issues\n---\nInstructions\n")
    (commands_dir / "pre-commit.md").write_text("---\ndescription: Run pre-commit checks\n---\nInstructions\n")

    result = _scan_commands_directory(commands_dir)
    assert result == [
        SkillInfo(
            name="fix-style",
            description="Fix style issues",
            source="custom",
            file_path=str(commands_dir / "fix-style.md"),
        ),
        SkillInfo(
            name="pre-commit",
            description="Run pre-commit checks",
            source="custom",
            file_path=str(commands_dir / "pre-commit.md"),
        ),
    ]


def test_scan_commands_directory_uses_filename_as_name(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "my-command.md").write_text("Just markdown, no frontmatter\n")

    result = _scan_commands_directory(commands_dir)
    assert result == [
        SkillInfo(name="my-command", description="", source="custom", file_path=str(commands_dir / "my-command.md")),
    ]


def test_scan_commands_directory_ignores_non_markdown_files(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "notes.txt").write_text("Not a command\n")
    (commands_dir / "script.py").write_text("# Not a command\n")
    (commands_dir / "real-command.md").write_text("---\ndescription: Real command\n---\n")

    result = _scan_commands_directory(commands_dir)
    assert len(result) == 1
    assert result[0].name == "real-command"


def test_scan_commands_directory_ignores_subdirectories(tmp_path: Path) -> None:
    commands_dir = tmp_path / ".claude" / "commands"
    subdir = commands_dir / "subdir"
    subdir.mkdir(parents=True)
    (subdir / "nested.md").write_text("Should be ignored\n")

    result = _scan_commands_directory(commands_dir)
    assert result == []


def test_scan_commands_directory_returns_empty_for_missing_directory(tmp_path: Path) -> None:
    result = _scan_commands_directory(tmp_path / "nonexistent")
    assert result == []


def test_discover_skills_combines_skills_and_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Create a skill
    skill_dir = tmp_path / ".claude" / "skills" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: alpha\ndescription: A skill\n---\n")

    # Create a command
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "beta.md").write_text("---\ndescription: A command\n---\n")

    result = discover_skills(tmp_path)
    assert result == [
        SkillInfo(name="alpha", description="A skill", source="custom", file_path=str(skill_dir / "SKILL.md")),
        SkillInfo(name="beta", description="A command", source="custom", file_path=str(commands_dir / "beta.md")),
    ]


def test_discover_skills_deduplicates_by_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Skills from the repo take precedence over commands with the same name."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Create a skill named "deploy"
    skill_dir = tmp_path / ".claude" / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: deploy\ndescription: Skill version\n---\n")

    # Create a command also named "deploy"
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "deploy.md").write_text("---\ndescription: Command version\n---\n")

    result = discover_skills(tmp_path)
    assert len(result) == 1
    assert result[0].name == "deploy"
    assert result[0].description == "Skill version"


def test_discover_skills_sorts_by_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    skills_dir = tmp_path / ".claude" / "skills"

    for name in ["zebra", "apple", "mango"]:
        d = skills_dir / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name}\n---\n")

    result = discover_skills(tmp_path)
    names = [s.name for s in result]
    assert names == ["apple", "mango", "zebra"]


def test_discover_skills_returns_empty_when_no_claude_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    result = discover_skills(tmp_path)
    assert result == []


def test_discover_skills_includes_home_directory_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Skills from ~/.claude/ are included alongside repo skills."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    # Repo skill
    repo_dir = tmp_path / "repo"
    skill_dir = repo_dir / ".claude" / "skills" / "repo-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: repo-skill\ndescription: From repo\n---\n")

    # Home skill
    home_skill_dir = fake_home / ".claude" / "skills" / "home-skill"
    home_skill_dir.mkdir(parents=True)
    (home_skill_dir / "SKILL.md").write_text("---\nname: home-skill\ndescription: From home\n---\n")

    # Home command
    home_commands_dir = fake_home / ".claude" / "commands"
    home_commands_dir.mkdir(parents=True)
    (home_commands_dir / "home-command.md").write_text("---\ndescription: Home command\n---\n")

    result = discover_skills(repo_dir)
    names = [s.name for s in result]
    assert "repo-skill" in names
    assert "home-skill" in names
    assert "home-command" in names


def test_discover_skills_repo_skills_take_precedence_over_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a skill exists in both repo and home, the repo version wins."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    repo_dir = tmp_path / "repo"

    # Repo skill named "shared"
    skill_dir = repo_dir / ".claude" / "skills" / "shared"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: shared\ndescription: Repo version\n---\n")

    # Home skill also named "shared"
    home_skill_dir = fake_home / ".claude" / "skills" / "shared"
    home_skill_dir.mkdir(parents=True)
    (home_skill_dir / "SKILL.md").write_text("---\nname: shared\ndescription: Home version\n---\n")

    result = discover_skills(repo_dir)
    assert len(result) == 1
    assert result[0].description == "Repo version"


def test_discover_skills_repo_command_takes_precedence_over_home_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cross-source precedence: a repo command shadows a home skill of the same name."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    repo_dir = tmp_path / "repo"

    # Repo *command* named "shared"
    repo_commands = repo_dir / ".claude" / "commands"
    repo_commands.mkdir(parents=True)
    (repo_commands / "shared.md").write_text("---\ndescription: Repo command\n---\n")

    # Home *skill* also named "shared"
    home_skill_dir = fake_home / ".claude" / "skills" / "shared"
    home_skill_dir.mkdir(parents=True)
    (home_skill_dir / "SKILL.md").write_text("---\nname: shared\ndescription: Home skill\n---\n")

    result = discover_skills(repo_dir)
    assert len(result) == 1
    assert result[0].description == "Repo command"


def _write_plugin_json(plugin_dir: Path, name: str) -> None:
    """Helper: write a minimal .claude-plugin/plugin.json so the namespace is derived."""
    plugin_json = plugin_dir / ".claude-plugin" / "plugin.json"
    plugin_json.parent.mkdir(parents=True, exist_ok=True)
    plugin_json.write_text(f'{{"name": "{name}", "version": "1.0.0"}}')


def test_discover_skills_namespaces_plugin_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plugin skills are namespaced with the plugin's name from plugin.json and carry their source/file_path through."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    plugin_dir = tmp_path / "plugin"
    _write_plugin_json(plugin_dir, "sculptor")
    plugin_skill_md = plugin_dir / "skills" / "fix-bug" / "SKILL.md"
    plugin_skill_md.parent.mkdir(parents=True)
    plugin_skill_md.write_text("---\nname: fix-bug\ndescription: Plugin fix-bug\n---\n")

    result = discover_skills(tmp_path / "repo", plugin_dirs=[plugin_dir])
    assert result == [
        SkillInfo(
            name="sculptor:fix-bug",
            description="Plugin fix-bug",
            source="plugin",
            file_path=str(plugin_skill_md),
        ),
    ]


def test_discover_skills_plugin_does_not_shadow_unprefixed_repo_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A plugin skill `fix-bug` is namespaced to `sculptor:fix-bug`, so a repo skill
    with the bare name `fix-bug` still appears alongside it."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    plugin_dir = tmp_path / "plugin"
    _write_plugin_json(plugin_dir, "sculptor")
    plugin_skill_md = plugin_dir / "skills" / "fix-bug" / "SKILL.md"
    plugin_skill_md.parent.mkdir(parents=True)
    plugin_skill_md.write_text("---\nname: fix-bug\ndescription: Plugin version\n---\n")

    repo_dir = tmp_path / "repo"
    repo_skill_md = repo_dir / ".claude" / "skills" / "fix-bug" / "SKILL.md"
    repo_skill_md.parent.mkdir(parents=True)
    repo_skill_md.write_text("---\nname: fix-bug\ndescription: Repo version\n---\n")

    result = discover_skills(repo_dir, plugin_dirs=[plugin_dir])
    names = sorted(s.name for s in result)
    assert names == ["fix-bug", "sculptor:fix-bug"]


def test_get_skill_source_directories_lists_repo_and_home_in_order() -> None:
    """The repo/home sources appear in discover order with the right kinds."""
    repo = Path("/repo")
    home = Path("/home/dev")
    result = get_skill_source_directories(repo, home_path=home)
    assert result == [
        (repo / ".claude" / "skills", SkillSourceKind.SKILL_DIR, None),
        (repo / ".claude" / "commands", SkillSourceKind.COMMAND_FILES, None),
        (home / ".claude" / "skills", SkillSourceKind.SKILL_DIR, None),
        (home / ".claude" / "commands", SkillSourceKind.COMMAND_FILES, None),
    ]


def test_get_skill_source_directories_puts_plugins_first_with_namespace(tmp_path: Path) -> None:
    """Plugin `skills/` dirs come first, tagged SKILL_DIR with the plugin namespace."""
    plugin_dir = tmp_path / "plugin"
    _write_plugin_json(plugin_dir, "sculptor")
    repo = tmp_path / "repo"
    home = tmp_path / "home"

    result = get_skill_source_directories(repo, plugin_dirs=[plugin_dir], home_path=home)

    assert result[0] == (plugin_dir / "skills", SkillSourceKind.SKILL_DIR, "sculptor")
    # The repo/home sources follow the plugin source.
    assert [s.path for s in result[1:]] == [
        repo / ".claude" / "skills",
        repo / ".claude" / "commands",
        home / ".claude" / "skills",
        home / ".claude" / "commands",
    ]


def test_get_skill_source_directories_defaults_home_to_path_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting home_path falls back to Path.home() (matches discover_skills)."""
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    result = get_skill_source_directories(tmp_path / "repo")
    home_sources = [s.path for s in result if str(s.path).startswith(str(fake_home))]
    assert home_sources == [fake_home / ".claude" / "skills", fake_home / ".claude" / "commands"]


def test_discover_skills_namespaces_multiple_plugins_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two plugin dirs produce namespaced skills under each plugin's own name."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    plugin_a = tmp_path / "plugin-a"
    _write_plugin_json(plugin_a, "sculptor")
    a_skill = plugin_a / "skills" / "help" / "SKILL.md"
    a_skill.parent.mkdir(parents=True)
    a_skill.write_text("---\nname: help\ndescription: Help skill\n---\n")

    plugin_b = tmp_path / "plugin-b"
    _write_plugin_json(plugin_b, "sculptor-workflow")
    b_skill = plugin_b / "skills" / "spec" / "SKILL.md"
    b_skill.parent.mkdir(parents=True)
    b_skill.write_text("---\nname: spec\ndescription: Spec skill\n---\n")

    result = discover_skills(tmp_path / "repo", plugin_dirs=[plugin_a, plugin_b])
    names = sorted(s.name for s in result)
    assert names == ["sculptor-workflow:spec", "sculptor:help"]
