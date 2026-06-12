#!/usr/bin/env bash
# This script builds a standalone executable for the sculpt CLI using PyInstaller.
# We need to build for multiple architectures, so we accept a python key argument to select the architecture that uv will use. By default it will use the system default python.
set -euxo pipefail

cd "$(dirname "$0")/../../tools/sculpt"

# The generated API client must exist before PyInstaller can bundle it.
# When invoked via `just sculpt-binary`, the recipe dependency on
# `generate-sculpt-client` handles this. When running the script directly,
# the caller must generate the client first.
if [[ ! -d "sculpt/client" ]]; then
  echo "ERROR: Generated API client not found at tools/sculpt/sculpt/client/."
  echo "Run 'just generate-sculpt-client' first, or use 'just sculpt-binary'."
  exit 1
fi

PYKEY="${1:-}"

# Let's create a temporary virtual environment for the build process.
TEMP_ENV="$(mktemp -d -t sculpt-venv.XXXXXX)"
trap 'rm -rf "$TEMP_ENV"' EXIT

# If no PYKEY was provided, choose a deterministic default on macOS
if [[ -z "$PYKEY" && "$(uname -s)" == "Darwin" ]]; then
  PYKEY="cpython-3.11.13-macos-aarch64-none"
elif [[ -z "$PYKEY" ]]; then
  PYKEY="3.11.13"
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

# Set the path correctly for brew-installed utils depending on if we are using arch or not
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
pyinstaller --onedir --name sculpt \
  --collect-all sculpt \
  --copy-metadata sculpt \
  --noupx \
  --noconfirm \
  sculpt/main.py

# Copy the output to sculptor/dist/sculpt/ so Electron forge can find it
DEST_DIR="$(dirname "$0")/../dist/sculpt"
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R dist/sculpt/* "$DEST_DIR/"

# Verify the build was for the correct architecture.
if [[ "$(uname -s)" == "Darwin" ]]; then
   if [[ "$PYKEY" == *"-x86_64-"* ]]; then
    echo "==> Verifying x86_64 architecture for sculpt"
    file "$DEST_DIR/sculpt" | grep "x86_64" || (echo "ERROR: sculpt is not x86_64!" && exit 1)
   else
    echo "==> Verifying arm64 architecture for sculpt"
    file "$DEST_DIR/sculpt" | grep "arm64" || (echo "ERROR: sculpt is not arm64!" && exit 1)
   fi
else
   echo "==> Non-macOS build, skipping architecture verification"
fi
