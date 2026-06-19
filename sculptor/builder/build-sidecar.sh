#!/usr/bin/env bash
# This script builds a standalone executable for the sculptor backend using PyInstaller.
# We need to build for multiple architectures, so we accept a python key argument to select the architecture that uv will use. By default it will use the system default python.
set -euxo pipefail

cd "$(dirname "$0")/.."

PYKEY="${1:-}"

# Let's create a temporary virtual environment for the build process.
TEMP_ENV="$(mktemp -d -t sculptor-venv.XXXXXX)"
trap 'rm -rf "$TEMP_ENV"' EXIT

# If no PYKEY was provided, choose a deterministic default on macOS
if [[ -z "$PYKEY" && "$(uname -s)" == "Darwin" ]]; then
  PYKEY="cpython-3.14.4-macos-aarch64-none"
elif [[ -z "$PYKEY" ]]; then
  PYKEY="3.14.4"
fi

ARCH_PREFIX=""
if [[ "$(uname -s)" == "Darwin" ]]; then
  if [[ "$PYKEY" == *"-x86_64-"* ]]; then
    echo "==> Building for x86_64 architecture"
    ARCH_PREFIX="arch -x86_64"
  fi
else
  echo "==> Non-macOS-Intel build, using system default architecture"
fi

# Set the path correctly for brew-installed utils dependending on if we are using arch or not
if [[ -n "$ARCH_PREFIX" ]]; then # if ARCH_PREFIX is set, we are on macOS and using arch
  export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
else
    echo "==> Not using arch, leaving PATH alone"
fi

# Ensure the requested interpreter exists and create a nonce env with it
$ARCH_PREFIX uv python install "$PYKEY" >/dev/null
$ARCH_PREFIX uv venv -p "$PYKEY" "$TEMP_ENV" --clear

export UV_PROJECT_ENVIRONMENT="$TEMP_ENV"

echo "==> Using ARCH_PREFIX: ${ARCH_PREFIX:-<none>}"
echo "==> Using uv python key: ${PYKEY:-<default>}"
echo "==> Using UV_PROJECT_ENVIRONMENT: $UV_PROJECT_ENVIRONMENT"

# Install dependencies into the nonce env
$ARCH_PREFIX uv sync --no-dev --extra packaging

# Time to build.
$ARCH_PREFIX uv run --no-dev --extra packaging \
pyinstaller --onedir --name sculptor_backend \
  --collect-all coolname \
  --copy-metadata coolname \
  --collect-all sculptor \
  --copy-metadata sculptor \
  --hidden-import sculptor._version \
  --hidden-import sculptor.database.alembic \
  --hidden-import sculptor.cli.app \
  --hidden-import sculptor.services.workspace_service.environment_manager.environments.pty_helper \
  --hidden-import yaml \
  --add-data "frontend-dist:frontend-dist" \
  --add-data "sculptor-plugin:sculptor-plugin" \
  --add-data "sculptor-workflow:sculptor-workflow" \
  --add-data "sculptor-experimental:sculptor-experimental" \
  --add-data "../samples/terminal_agents:samples/terminal_agents" \
  --noupx \
  --noconfirm \
  sculptor/cli/main.py

# Verify the build was for the correct architecture.
if [[ "$(uname -s)" == "Darwin" ]]; then
   if [[ "$PYKEY" == *"-x86_64-"* ]]; then
    echo "==> Verifying x86_64 architecture for sculptor_backend"
    file dist/sculptor_backend/sculptor_backend | grep "x86_64" || (echo "ERROR: sculptor_backend is not x86_64!" && exit 1)
   else
    echo "==> Verifying arm64 architecture for sculptor_backend"
    file dist/sculptor_backend/sculptor_backend | grep "arm64" || (echo "ERROR: sculptor_backend is not arm64!" && exit 1)
   fi
else
   echo "==> Non-macOS build, skipping architecture verification"
fi
