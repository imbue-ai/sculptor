#!/bin/bash
#
# Download a Sculptor AppImage and extract the backend and sculpt CLI binaries.
#
# Usage:
#   ./download-sculptor-backend.sh <version> [output-dir]
#
# Arguments:
#   version    — Sculptor version to download (e.g., "0.3.1").
#                Use "latest" to fetch the current stable version.
#   output-dir — Directory to extract binaries into (default: ./sculptor_backend).
#
# The output directory will contain:
#   sculptor_backend/sculptor_backend   — the backend binary + _internal/
#   sculpt/sculpt                       — the sculpt CLI binary + _internal/
#
# These are self-contained PyInstaller bundles — no Python needed at runtime.
#
# Environment:
#   SCULPTOR_CHANNEL — release channel: "slim" (stable, default) or "slim-rc" (RC)
#
# Examples:
#   ./download-sculptor-backend.sh latest
#   ./download-sculptor-backend.sh 0.3.1 /opt/sculptor

set -euo pipefail

S3_BASE_URL="https://imbue-sculptor-releases.s3.us-west-2.amazonaws.com"

# Default to slim (stable). If the version string contains "rc", use slim-rc.
# SCULPTOR_CHANNEL env var overrides this heuristic.
CHANNEL="${SCULPTOR_CHANNEL:-slim}"

log() { echo "[download-sculptor-backend] $*" >&2; }

usage() {
  echo "Usage: $0 <version|latest> [output-dir]" >&2
  exit 1
}

if [ $# -lt 1 ]; then
  usage
fi

# ---------------------------------------------------------------------------
# AppImages are Linux ELF binaries — extraction requires a matching host
# ---------------------------------------------------------------------------
if [ "$(uname -s)" != "Linux" ]; then
  log "ERROR: AppImage extraction requires Linux (detected: $(uname -s))"
  log "Run this script inside a Linux container or VM."
  exit 1
fi

MACHINE=$(uname -m)
case "$MACHINE" in
  x86_64)
    ARCH="x64"
    MANIFEST_PATH="AppImage/x64/latest-linux.yml"
    ;;
  aarch64)
    ARCH="arm64"
    MANIFEST_PATH="AppImage/arm64/latest-linux-arm64.yml"
    ;;
  *)
    log "ERROR: Unsupported architecture: $MACHINE"
    exit 1
    ;;
esac

VERSION="$1"
OUTPUT_DIR="${2:-./sculptor_backend}"

# Normalize Electron's semver format (0.19.0-rc.1) to the AppImage filename
# format (0.19.0rc1). Electron uses hyphens and dots in pre-release tags,
# but the published filenames don't.
VERSION=$(echo "$VERSION" | sed 's/-rc\.\([0-9]*\)/rc\1/')

# If SCULPTOR_CHANNEL wasn't explicitly set, infer from the version string.
if [ -z "${SCULPTOR_CHANNEL:-}" ] && echo "$VERSION" | grep -qi "rc"; then
  CHANNEL="slim-rc"
fi

# ---------------------------------------------------------------------------
# Resolve "latest" to an actual version by reading the update manifest
# ---------------------------------------------------------------------------
if [ "$VERSION" = "latest" ]; then
  MANIFEST_URL="${S3_BASE_URL}/${CHANNEL}/${MANIFEST_PATH}"
  log "Fetching manifest from $MANIFEST_URL"

  MANIFEST=$(curl -fsSL "$MANIFEST_URL")
  VERSION=$(echo "$MANIFEST" | grep '^version:' | awk '{print $2}')

  if [ -z "$VERSION" ]; then
    log "ERROR: Could not parse version from manifest"
    echo "$MANIFEST" >&2
    exit 1
  fi

  log "Latest version: $VERSION"
fi

# ---------------------------------------------------------------------------
# Skip if the output directory already has this version
# ---------------------------------------------------------------------------
VERSION_MARKER="$OUTPUT_DIR/.sculptor-version"

if [ -f "$VERSION_MARKER" ] && [ "$(cat "$VERSION_MARKER")" = "$VERSION" ]; then
  log "Version $VERSION already extracted in $OUTPUT_DIR (skipping download)"
  exit 0
fi

# ---------------------------------------------------------------------------
# Download the AppImage into a temp dir, extract, then copy out the binaries
# ---------------------------------------------------------------------------
FILENAME="Sculptor-${VERSION}.AppImage"
DOWNLOAD_URL="${S3_BASE_URL}/${CHANNEL}/AppImage/${ARCH}/${FILENAME}"

TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT
APPIMAGE_PATH="${TEMP_DIR}/${FILENAME}"

log "Downloading $DOWNLOAD_URL"
curl -fSL --progress-bar -o "$APPIMAGE_PATH" "$DOWNLOAD_URL"
chmod +x "$APPIMAGE_PATH"

# ---------------------------------------------------------------------------
# Extract the AppImage
# ---------------------------------------------------------------------------
log "Extracting AppImage (this may take a moment)..."
(cd "$TEMP_DIR" && "$APPIMAGE_PATH" --appimage-extract >/dev/null)

# Electron Forge AppImages place resources under usr/lib/<name>/resources/
SQUASHFS_ROOT="$TEMP_DIR/squashfs-root"
RESOURCES="$SQUASHFS_ROOT/usr/lib/sculptor/resources"

if [ ! -d "$RESOURCES" ]; then
  log "ERROR: resources/ directory not found in extracted AppImage"
  ls -la "$SQUASHFS_ROOT/" >&2 || true
  exit 1
fi

# ---------------------------------------------------------------------------
# Copy sculptor_backend
# ---------------------------------------------------------------------------
BACKEND_SRC="$RESOURCES/sculptor_backend"

if [ ! -f "$BACKEND_SRC/sculptor_backend" ]; then
  log "ERROR: sculptor_backend binary not found at $BACKEND_SRC/sculptor_backend"
  ls -la "$RESOURCES/" >&2 || true
  exit 1
fi

mkdir -p "$OUTPUT_DIR/sculptor_backend"
log "Copying sculptor_backend to $OUTPUT_DIR/sculptor_backend"
cp -a "$BACKEND_SRC/." "$OUTPUT_DIR/sculptor_backend/"
chmod +x "$OUTPUT_DIR/sculptor_backend/sculptor_backend"

# ---------------------------------------------------------------------------
# Copy sculpt CLI (if present)
# ---------------------------------------------------------------------------
SCULPT_SRC="$RESOURCES/sculpt"

if [ -f "$SCULPT_SRC/sculpt" ]; then
  mkdir -p "$OUTPUT_DIR/sculpt"
  log "Copying sculpt CLI to $OUTPUT_DIR/sculpt"
  cp -a "$SCULPT_SRC/." "$OUTPUT_DIR/sculpt/"
  chmod +x "$OUTPUT_DIR/sculpt/sculpt"
else
  log "WARNING: sculpt CLI not found in AppImage (skipping)"
fi

# ---------------------------------------------------------------------------
# Write version marker so subsequent runs can skip the download
# ---------------------------------------------------------------------------
echo "$VERSION" > "$VERSION_MARKER"

log "Done! Extracted to $OUTPUT_DIR"
log "  Backend: $OUTPUT_DIR/sculptor_backend/sculptor_backend"
if [ -f "$OUTPUT_DIR/sculpt/sculpt" ]; then
  log "  Sculpt:  $OUTPUT_DIR/sculpt/sculpt"
fi
