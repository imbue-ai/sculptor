from pathlib import Path

import sculptor


def get_plugin_dirs() -> list[Path]:
    """Return the list of bundled plugin directories that exist on disk.

    Sculptor ships three plugins:
      - `sculptor-plugin` — runtime helpers (/help, /sculpt-cli)
      - `sculptor-workflow` — opinionated engineering workflow
        (/spec, /mock, /architect, /plan, /build, /review, /fix-bug,
        /setup-repo)
      - `sculptor-experimental` — experimental sculpt-CLI skills
        (/sculptor-experimental:stack, /sculptor-experimental:handoff)

    Each plugin is loaded into Claude Code via a separate `--plugin-dir`
    flag in `get_claude_command()`.
    """
    base = Path(sculptor.__file__).parent.parent
    candidates = [base / "sculptor-plugin", base / "sculptor-workflow", base / "sculptor-experimental"]
    return [path for path in candidates if path.is_dir()]
