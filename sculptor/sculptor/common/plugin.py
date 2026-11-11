from pathlib import Path
from typing import Literal
from typing import assert_never

import sculptor

VcsKind = Literal["git", "jj"]
"""The version control system a workspace's checkout is managed with."""


def get_plugins_base_dir() -> Path:
    """The directory containing the bundled plugin directories.

    Resolves to `<repo>/sculptor/` when running from source and to the
    PyInstaller `_internal/` directory in the packaged app. Also exported to
    terminal agents as the `SCULPT_PLUGINS_DIR` env var so registration
    launch commands can reference the bundled plugins without baking in
    per-machine paths (which would rot on app updates and AppImage mounts).
    """
    return Path(sculptor.__file__).parent.parent


def _get_jj_plugin_dir() -> Path:
    return get_plugins_base_dir() / "sculptor-jj"


def get_plugin_dirs(vcs_kind: VcsKind) -> list[Path]:
    """Return the bundled plugin directories for a workspace that exist on disk.

    Every workspace gets three plugins:
      - `sculptor-plugin` — runtime helpers (/help, /sculpt-cli,
        /build-sculptor-extension)
      - `sculptor-workflow` — opinionated engineering workflow
        (/spec, /mock, /architect, /plan, /build, /review, /fix-bug,
        /setup-repo)
      - `sculptor-experimental` — experimental sculpt-CLI skills
        (/sculptor-experimental:stack, /sculptor-experimental:handoff)

    jj workspaces also get `sculptor-jj`, the vendored jujutsu skill. Its
    description asks to be activated on any VCS operation, so it stays out of
    git workspaces. It comes last because FakeClaude reads only the first
    `--plugin-dir`.

    Each plugin is loaded into Claude Code via a separate `--plugin-dir`
    flag in `get_claude_command()`.
    """
    base = get_plugins_base_dir()
    candidates = [base / "sculptor-plugin", base / "sculptor-workflow", base / "sculptor-experimental"]
    match vcs_kind:
        case "git":
            pass
        case "jj":
            candidates.append(_get_jj_plugin_dir())
        case _ as unreachable:
            assert_never(unreachable)
    return [path for path in candidates if path.is_dir()]


def get_terminal_agent_plugin_env(vcs_kind: VcsKind) -> dict[str, str]:
    """The env vars terminal-agent launch commands use to find the bundled plugins.

    `SCULPT_JJ_PLUGIN_DIR` is set only in jj workspaces, so a registration can
    pass it to `--plugin-dir` exactly when it is present.
    """
    plugin_env = {"SCULPT_PLUGINS_DIR": str(get_plugins_base_dir())}
    match vcs_kind:
        case "git":
            pass
        case "jj":
            plugin_env["SCULPT_JJ_PLUGIN_DIR"] = str(_get_jj_plugin_dir())
        case _ as unreachable:
            assert_never(unreachable)
    return plugin_env
