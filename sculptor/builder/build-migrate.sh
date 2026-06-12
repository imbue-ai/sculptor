#!/usr/bin/env bash
# This script builds a standalone executable for the migration script using PyInstaller.
# The migration script is stdlib-only, so no extra dependencies are needed beyond PyInstaller.
# We accept a python key argument to select the architecture that uv will use.
set -euxo pipefail

cd "$(dirname "$0")/../.."

PYKEY="${1:-}"

# Let's create a temporary virtual environment for the build process.
TEMP_ENV="$(mktemp -d -t migrate-venv.XXXXXX)"
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
if [[ -n "$ARCH_PREFIX" ]]; then
  export PATH="/usr/local/bin:/usr/local/sbin:$PATH"
else
  echo "==> Not using arch, leaving PATH alone"
fi

# Ensure the requested interpreter exists and create a nonce env with it
$ARCH_PREFIX uv python install "$PYKEY" >/dev/null
$ARCH_PREFIX uv venv -p "$PYKEY" "$TEMP_ENV" --clear

echo "==> Using ARCH_PREFIX: ${ARCH_PREFIX:-<none>}"
echo "==> Using uv python key: ${PYKEY:-<default>}"
echo "==> Using VIRTUAL_ENV: $TEMP_ENV"

# Install only PyInstaller (the migration script uses only stdlib)
$ARCH_PREFIX uv pip install --python "$TEMP_ENV/bin/python" pyinstaller

# Build the migration binary
$ARCH_PREFIX "$TEMP_ENV/bin/pyinstaller" --onedir --name sculptor_migrate \
  --noupx \
  --noconfirm \
  scripts/migrate_sculptor_folder.py

# Copy the output to sculptor/dist/sculptor_migrate/ so Electron forge can find it
DEST_DIR="$(dirname "$0")/../dist/sculptor_migrate"
rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
cp -R dist/sculptor_migrate/* "$DEST_DIR/"

# Clean up PyInstaller artifacts from the repo root
rm -rf dist/sculptor_migrate build/sculptor_migrate sculptor_migrate.spec

# Verify the build was for the correct architecture.
if [[ "$(uname -s)" == "Darwin" ]]; then
  if [[ "$PYKEY" == *"-x86_64-"* ]]; then
    echo "==> Verifying x86_64 architecture for sculptor_migrate"
    file "$DEST_DIR/sculptor_migrate" | grep "x86_64" || (echo "ERROR: sculptor_migrate is not x86_64!" && exit 1)
  else
    echo "==> Verifying arm64 architecture for sculptor_migrate"
    file "$DEST_DIR/sculptor_migrate" | grep "arm64" || (echo "ERROR: sculptor_migrate is not arm64!" && exit 1)
  fi
else
  echo "==> Non-macOS build, skipping architecture verification"
fi
