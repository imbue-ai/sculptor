"""Discovery logic for Claude Code skills and commands.

Scans for skills in .claude/skills/ (directory-based with SKILL.md) and
commands in .claude/commands/ (flat markdown files), from both the repo
and the user's home directory (~/.claude).
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

import yaml
from loguru import logger

from sculptor.web.data_types import SkillInfo


def _get_plugin_namespace(plugin_dir: Path) -> str:
    """Read the plugin's namespace from .claude-plugin/plugin.json, fall back to dir name."""
    plugin_json = plugin_dir / ".claude-plugin" / "plugin.json"
    try:
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return plugin_dir.name
    if isinstance(data, dict):
        name = data.get("name")
        if isinstance(name, str) and name:
            return name
    return plugin_dir.name


def _parse_skill_frontmatter(content: str) -> tuple[str | None, str | None]:
    """Extract name and description from SKILL.md YAML frontmatter."""
    if not content.startswith("---"):
        return None, None

    end_index = content.find("---", 3)
    if end_index == -1:
        return None, None

    frontmatter_text = content[3:end_index].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None, None
    if not isinstance(frontmatter, dict):
        return None, None

    name = frontmatter.get("name")
    description = frontmatter.get("description")

    # YAML can deserialize these fields to ints, lists, or dicts (e.g. a stray
    # `description: 42`). Coercing to str via `str()` would mask the malformed
    # input; rejecting outright keeps the loop's silent-skip semantics intact.
    if not isinstance(name, str):
        return None, None
    if description is not None and not isinstance(description, str):
        description = None
    if isinstance(description, str):
        description = description.strip()

    return name, description


def _parse_command_frontmatter(content: str) -> str | None:
    """Extract description from a command markdown file's YAML frontmatter.

    Commands use a simpler format than skills: the filename is the command name,
    and the frontmatter may optionally contain a description field.
    """
    if not content.startswith("---"):
        return None

    end_index = content.find("---", 3)
    if end_index == -1:
        return None

    frontmatter_text = content[3:end_index].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return None
    if not isinstance(frontmatter, dict):
        return None

    description = frontmatter.get("description")
    if isinstance(description, str):
        return description.strip()
    return None


def _scan_skills_directory(skills_dir: Path, source: Literal["custom", "plugin"] = "custom") -> list[SkillInfo]:
    """Scan a .claude/skills/ directory for SKILL.md files and parse their frontmatter."""
    if not skills_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            content = skill_md.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Failed to read {}: {}", skill_md, e)
            continue
        name, description = _parse_skill_frontmatter(content)
        # Claude Code identifies a skill by its directory name and parses
        # frontmatter leniently — a SKILL.md with missing or malformed
        # frontmatter is still a valid skill. Match that behavior instead of
        # silently dropping such skills (SCU-1302): fall back to the directory
        # name when the frontmatter yields no usable name.
        if name is None:
            name = skill_dir.name
        skills.append(SkillInfo(name=name, description=description or "", source=source, file_path=str(skill_md)))

    return skills


def _scan_commands_directory(commands_dir: Path, source: Literal["custom", "plugin"] = "custom") -> list[SkillInfo]:
    """Scan a .claude/commands/ directory for markdown command files.

    Commands are flat .md files where the filename (without extension) is
    the command name. An optional YAML frontmatter block may contain a
    description field.
    """
    if not commands_dir.is_dir():
        return []

    skills: list[SkillInfo] = []
    for command_file in sorted(commands_dir.iterdir()):
        if not command_file.is_file():
            continue
        if command_file.suffix != ".md":
            continue
        try:
            content = command_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug("Failed to read {}: {}", command_file, e)
            continue
        name = command_file.stem
        description = _parse_command_frontmatter(content) or ""
        skills.append(SkillInfo(name=name, description=description, source=source, file_path=str(command_file)))

    return skills


def discover_skills(repo_path: Path, plugin_dirs: Sequence[Path] = ()) -> list[SkillInfo]:
    """Discover all skills and commands from the plugins, repo, and home directory.

    Searches these locations in order:
    0. <plugin>/skills/          (plugin skills, namespaced with the
                                  plugin's name from .claude-plugin/plugin.json)
    1. <repo>/.claude/skills/    (directory-based, SKILL.md)
    2. <repo>/.claude/commands/  (flat markdown files)
    3. ~/.claude/skills/         (directory-based, SKILL.md)
    4. ~/.claude/commands/       (flat markdown files)

    Multiple plugin dirs can be passed; each one is scanned with its own
    namespace prefix. Skills from later sources are only included if not
    already present (by namespaced name) from earlier sources. The final
    list is sorted by name.
    """
    seen_names: set[str] = set()
    all_skills: list[SkillInfo] = []

    for plugin_dir in plugin_dirs:
        namespace = _get_plugin_namespace(plugin_dir)
        for skill in _scan_skills_directory(plugin_dir / "skills", source="plugin"):
            namespaced = SkillInfo(
                name=f"{namespace}:{skill.name}",
                description=skill.description,
                source=skill.source,
                file_path=skill.file_path,
            )
            if namespaced.name in seen_names:
                continue
            seen_names.add(namespaced.name)
            all_skills.append(namespaced)

    search_paths = [
        (repo_path / ".claude" / "skills", _scan_skills_directory),
        (repo_path / ".claude" / "commands", _scan_commands_directory),
        (Path.home() / ".claude" / "skills", _scan_skills_directory),
        (Path.home() / ".claude" / "commands", _scan_commands_directory),
    ]

    for directory, scanner in search_paths:
        for skill in scanner(directory):
            if skill.name not in seen_names:
                seen_names.add(skill.name)
                all_skills.append(skill)

    all_skills.sort(key=lambda s: s.name)
    return all_skills
