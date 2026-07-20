"""Shared paths and knobs for the demo pipeline.

Everything the pipeline writes lives under one demo directory (default
~/.cache/sculptor-demo) so a run never touches the user's real repos or
Sculptor instance:

  <demo dir>/
  ├── repos/<name>/       fresh clones the demo workspaces are created in
  ├── screenshots/        harness screenshots + port files + server log
  └── gh_fixtures.json    canned PR status served by marketing/gh_shim/gh

Environment knobs:
  SCULPTOR_DEMO_DIR            override the demo directory
  SCULPTOR_DEMO_REPO_<NAME>    local clone source for an optional extra repo
                               (e.g. SCULPTOR_DEMO_REPO_OPENHOST=~/code/openhost);
                               repos without a source are skipped
  HARNESS_BACKEND_PORT         talk to an explicitly given backend instead of
                               the port file written by the harness
"""

from __future__ import annotations

import os
from pathlib import Path

# marketing/seed/config.py -> repo root is two levels up from marketing/.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Under the user's cache dir, not /tmp: the demo dir holds full clones of the
# user's local repos, which don't belong in a world-readable location.
DEMO_DIR = Path(os.environ.get("SCULPTOR_DEMO_DIR", "~/.cache/sculptor-demo")).expanduser()
REPOS_DIR = DEMO_DIR / "repos"
SCREENSHOTS_DIR = DEMO_DIR / "screenshots"
GH_FIXTURES_PATH = DEMO_DIR / "gh_fixtures.json"
GH_SHIM_DIR = REPO_ROOT / "marketing" / "gh_shim"

CONTROL_PORT_FILE = SCREENSHOTS_DIR / "control_port.txt"
BACKEND_PORT_FILE = SCREENSHOTS_DIR / "backend_port.txt"
SERVER_LOG = SCREENSHOTS_DIR / "manual-test-server.log"
SERVER_PID_FILE = SCREENSHOTS_DIR / "manual-test-server.pid"

# The owner every demo clone's fake origin claims. PR polling only runs against
# github-shaped origins, and the gh shim's fixtures must name the same
# owner/repo, so this is the single source of truth for both.
FAKE_ORIGIN_OWNER = "imbue-ai"


def fake_origin_url(repo_name: str) -> str:
    return f"https://github.com/{FAKE_ORIGIN_OWNER}/{repo_name}.git"


def repo_clone_source(name: str) -> Path | None:
    """Resolve where to clone a demo repo from.

    The sculptor repo always clones from the checkout this pipeline runs in;
    other repos are opt-in via SCULPTOR_DEMO_REPO_<NAME> and skipped (with
    their workspaces) when unset or missing, so anyone can run the seed with
    just this repo.
    """
    if name == "sculptor":
        return REPO_ROOT
    source = os.environ.get(f"SCULPTOR_DEMO_REPO_{name.upper()}")
    if not source:
        return None
    path = Path(source).expanduser()
    return path if path.is_dir() else None
