"""Guards the jujutsu skill vendored into the sculptor-jj plugin.

`just update-jj-skill` mirrors the files from upstream and records their
digests in `UPSTREAM.toml`; a hand edit or a partial update fails here.
"""

import hashlib
import json
import tomllib

import yaml

from sculptor.common.plugin import get_plugins_base_dir

_JJ_PLUGIN_DIR = get_plugins_base_dir() / "sculptor-jj"
_SKILL_DIR = _JJ_PLUGIN_DIR / "skills" / "jujutsu"


def test_vendored_files_are_exactly_those_recorded_with_matching_digests() -> None:
    recorded = tomllib.loads((_JJ_PLUGIN_DIR / "UPSTREAM.toml").read_text())["sha256"]
    on_disk = {
        path.relative_to(_JJ_PLUGIN_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _SKILL_DIR.rglob("*")
        if path.is_file()
    }
    assert on_disk == recorded


def test_vendored_skill_is_named_jujutsu() -> None:
    _, frontmatter, _ = (_SKILL_DIR / "SKILL.md").read_text().split("---", 2)
    assert yaml.safe_load(frontmatter)["name"] == "jujutsu"


def test_plugin_manifest_names_the_plugin_sculptor_jj() -> None:
    manifest = json.loads((_JJ_PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "sculptor-jj"
