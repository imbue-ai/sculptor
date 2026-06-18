#!/bin/bash
# Finalize the offload base image. Runs as offload's `sandbox_init_cmd` after
# the Dockerfile builds the raw image and copies the source into /app, baking
# the slow-changing layer: dependency installs, tool stubs, and the empty
# /tmp/repo the integration-test fixtures expect. Per-run regeneration of
# derived artifacts (frontend api client + bundle, sculpt client) lives in
# offload.toml's `post_patch_cmd`, which runs after the thin-diff applies.
set -euo pipefail

source "$NVM_DIR/nvm.sh"

# Modal's in-cluster pypi mirror is fast but flaky: it intermittently 500s or
# stalls on wheel downloads. Fall back to public PyPI once on failure, and bound
# each attempt with a timeout so a silent stall can't hang the build.
uv_with_fallback() {
    if timeout --signal=KILL 600 uv "$@"; then
        return 0
    fi
    echo "uv $1 failed against Modal mirror; retrying once with public PyPI" >&2
    UV_DEFAULT_INDEX=https://pypi.org/simple timeout --signal=KILL 600 uv "$@"
}

# The real Claude CLI install + wrapper below are shadowed by the stub written
# at the end of this script.
timeout --signal=KILL 420 npm install -g @anthropic-ai/claude-code@latest

# Wrap claude so --version returns cleanly (for the onboarding dependency check)
# and everything else delegates to the real binary.
REAL_CLAUDE="$(npm root -g)/@anthropic-ai/claude-code/cli.js"
NODE_BIN="$(which node)"
cat > /usr/local/bin/claude <<WRAPPER
#!/bin/bash
case "\$1" in
    --version|-v)
        echo "claude-code 2.1.108"
        ;;
    *)
        exec $NODE_BIN $REAL_CLAUDE "\$@"
        ;;
esac
WRAPPER
chmod +x /usr/local/bin/claude

# Install the sculptor project's Python deps (tests run via
# `uv run --project sculptor pytest`).
uv_with_fallback sync --project sculptor --dev --all-extras

# Pre-install sculpt + its dev group (openapi-python-client) so post_patch_cmd
# can regenerate the client without re-fetching deps on every run.
uv_with_fallback pip install -e tools/sculpt
uv_with_fallback sync --project tools/sculpt --group dev

timeout --signal=KILL 600 uv run --project sculptor -m playwright install --with-deps chromium

# node_modules only; the api client + dist bundle are built later in
# offload.toml's post_patch_cmd.
(
  cd sculptor/frontend
  timeout --signal=KILL 600 npm ci
  node /app/scripts/fix-bin-wrappers.js
)

# Configure git and init /app as a repo for the integration-test fixtures.
cd /app
git config --global user.name test
git config --global user.email test@test.com
git config --global --add safe.directory /app
git -C /app init -q

# Replace claude with a stub the fixtures rely on: --version (onboarding check)
# and `auth status` (auth precheck) succeed, everything else fails.
CLAUDE_VER=$(timeout --signal=KILL 180 uv run --project sculptor python -c 'from sculptor.services.dependency_management_service import CLAUDE_VERSION_RANGE; print(CLAUDE_VERSION_RANGE.recommended_version)')
cat > /usr/local/bin/claude <<STUB
#!/bin/bash
case "\$1" in
    --version|-v) echo "claude $CLAUDE_VER"; exit 0;;
    auth) case "\$2" in status) echo "Authenticated"; exit 0;; *) exit 1;; esac;;
    *) echo "stub"; exit 1;;
esac
STUB
chmod +x /usr/local/bin/claude

# Seed an empty git repo at /tmp/repo (offload.toml's provider env points
# PROJECT_PATH here for the fixtures).
mkdir -p /tmp/repo
git init /tmp/repo
(cd /tmp/repo && git commit --allow-empty -m init)
