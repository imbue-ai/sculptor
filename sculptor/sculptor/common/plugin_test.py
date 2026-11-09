from pathlib import Path

from sculptor.common.plugin import VcsKind
from sculptor.common.plugin import get_plugin_dirs
from sculptor.common.plugin import get_plugins_base_dir
from sculptor.common.plugin import get_terminal_agent_plugin_env
from sculptor.web.skills import discover_skills


def test_git_workspaces_get_the_bundled_plugins_without_sculptor_jj() -> None:
    base = get_plugins_base_dir()
    assert get_plugin_dirs("git") == [
        base / "sculptor-plugin",
        base / "sculptor-workflow",
        base / "sculptor-experimental",
    ]


def test_jj_workspaces_get_sculptor_jj_after_every_other_plugin() -> None:
    assert get_plugin_dirs("jj") == [*get_plugin_dirs("git"), get_plugins_base_dir() / "sculptor-jj"]


def test_only_jj_workspaces_offer_the_jujutsu_skill(tmp_path: Path) -> None:
    def skill_names(vcs_kind: VcsKind) -> set[str]:
        return {skill.name for skill in discover_skills(tmp_path, plugin_dirs=get_plugin_dirs(vcs_kind))}

    assert "sculptor-jj:jujutsu" in skill_names("jj")
    assert "sculptor-jj:jujutsu" not in skill_names("git")


def test_terminal_agents_get_the_jj_plugin_dir_only_in_jj_workspaces() -> None:
    base = get_plugins_base_dir()
    assert get_terminal_agent_plugin_env("git") == {"SCULPT_PLUGINS_DIR": str(base)}
    assert get_terminal_agent_plugin_env("jj") == {
        "SCULPT_PLUGINS_DIR": str(base),
        "SCULPT_JJ_PLUGIN_DIR": str(base / "sculptor-jj"),
    }


def test_every_bundled_plugin_is_packaged_into_the_sidecar_and_the_linux_image() -> None:
    repo_root = get_plugins_base_dir().parent
    sidecar_build = (repo_root / "sculptor" / "builder" / "build-sidecar.sh").read_text()
    linux_image = (repo_root / "container" / "build-backend-linux.dockerfile").read_text()
    for plugin_dir in get_plugin_dirs("jj"):
        assert f'--add-data "{plugin_dir.name}:{plugin_dir.name}"' in sidecar_build
        assert f"COPY sculptor/{plugin_dir.name}/ sculptor/{plugin_dir.name}/" in linux_image
