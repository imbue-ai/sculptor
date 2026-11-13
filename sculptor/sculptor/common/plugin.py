from pathlib import Path

import sculptor


def get_plugins_base_dir() -> Path:
    """The directory containing the bundled plugin directories.

    Resolves to `<repo>/sculptor/` when running from source and to the
    PyInstaller `_internal/` directory in the packaged app. Also exported to
    terminal agents as the `SCULPT_PLUGINS_DIR` env var so registration
    launch commands can reference the bundled plugins without baking in
    per-machine paths (which would rot on app updates and AppImage mounts).
    """
    return Path(sculptor.__file__).parent.parent


def get_plugin_dirs() -> list[Path]:
    """Return the list of bundled plugin directories that exist on disk.

    Every agent gets the same four plugins:
      - `sculptor-plugin` — runtime helpers (/help, /sculpt-cli,
        /build-sculptor-extension)
      - `sculptor-workflow` — opinionated engineering workflow
        (/spec, /mock, /architect, /plan, /build, /review, /fix-bug,
        /setup-repo)
      - `sculptor-experimental` — experimental sculpt-CLI skills
        (/sculptor-experimental:stack, /sculptor-experimental:handoff)
      - `sculptor-jj` — the vendored jujutsu skill (/sculptor-jj:jujutsu)

    `sculptor-plugin` stays first because FakeClaude reads only the first
    `--plugin-dir`. Each plugin is loaded into Claude Code via a separate
    `--plugin-dir` flag in `get_claude_command()`.
    """
    base = get_plugins_base_dir()
    candidates = [
        base / "sculptor-plugin",
        base / "sculptor-workflow",
        base / "sculptor-experimental",
        base / "sculptor-jj",
    ]
    return [path for path in candidates if path.is_dir()]
