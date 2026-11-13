from pathlib import Path

from sculptor.common.plugin import get_plugin_dirs
from sculptor.common.plugin import get_plugins_base_dir
from sculptor.web.skills import discover_skills


def test_every_agent_gets_the_bundled_plugins_with_sculptor_jj_last() -> None:
    base = get_plugins_base_dir()
    assert get_plugin_dirs() == [
        base / "sculptor-plugin",
        base / "sculptor-workflow",
        base / "sculptor-experimental",
        base / "sculptor-jj",
    ]


def test_the_jujutsu_skill_is_offered_in_every_workspace(tmp_path: Path) -> None:
    skill_names = {skill.name for skill in discover_skills(tmp_path, plugin_dirs=get_plugin_dirs())}
    assert "sculptor-jj:jujutsu" in skill_names


def test_every_bundled_plugin_is_packaged_into_the_sidecar_and_the_linux_image() -> None:
    repo_root = get_plugins_base_dir().parent
    sidecar_build = (repo_root / "sculptor" / "builder" / "build-sidecar.sh").read_text()
    linux_image = (repo_root / "container" / "build-backend-linux.dockerfile").read_text()
    for plugin_dir in get_plugin_dirs():
        assert f'--add-data "{plugin_dir.name}:{plugin_dir.name}"' in sidecar_build
        assert f"COPY sculptor/{plugin_dir.name}/ sculptor/{plugin_dir.name}/" in linux_image
