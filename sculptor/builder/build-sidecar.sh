#!/usr/bin/env bash
# Builds the Sculptor backend sidecar.
#
# The backend was rewritten from Python to TypeScript, so this no longer runs
# PyInstaller: it stages a Node sidecar (esbuild bundle + pinned Node 24 runtime
# + prebuilt native addons) into dist/sculptor_backend — the same --onedir-style
# directory the Electron/Docker wrappers launch. The bundled launcher script is
# named `sculptor_backend` so those wrappers' launch contract is unchanged.
#
# Optional arg selects the target platform (macos-arm64 | linux-x64); for
# backwards compatibility a legacy python key containing "x86_64" maps to
# linux-x64. With no arg the host platform is used. macOS code signing runs when
# SIGN_IDENTITY is set (REQ-SEC-003); notarization stays in builder/darwin.py.
set -euxo pipefail

cd "$(dirname "$0")/.."
SCULPTOR_DIR="$(pwd)"
BACKEND_DIR="$SCULPTOR_DIR/backend"
OUT_DIR="$SCULPTOR_DIR/dist/sculptor_backend"

ARG="${1:-}"
case "$ARG" in
  macos-arm64|linux-x64) TARGET="$ARG" ;;
  *x86_64*) TARGET="linux-x64" ;; # legacy python-key compatibility
  "") TARGET="host" ;;
  *) TARGET="host" ;;
esac

echo "==> Building Node sidecar for target: $TARGET -> $OUT_DIR"
OUT_DIR="$OUT_DIR" SIDECAR_TARGET="$TARGET" SIGN_IDENTITY="${SIGN_IDENTITY:-}" \
  /usr/bin/env bash "$BACKEND_DIR/scripts/build-sidecar.sh"

# Bundle the resource directories the backend reads at runtime, matching the old
# PyInstaller --add-data set: the bundled skills/plugins and the terminal-agent
# samples (Task 7.5). frontend-dist is staged by the backend script.
echo "==> Bundling resource directories"
for RES in sculptor-plugin sculptor-workflow sculptor-experimental; do
  if [[ -d "$SCULPTOR_DIR/$RES" ]]; then
    rm -rf "${OUT_DIR:?}/$RES"
    cp -R "$SCULPTOR_DIR/$RES" "$OUT_DIR/$RES"
  fi
done
if [[ -d "$SCULPTOR_DIR/../samples/terminal_agents" ]]; then
  mkdir -p "$OUT_DIR/samples"
  rm -rf "$OUT_DIR/samples/terminal_agents"
  cp -R "$SCULPTOR_DIR/../samples/terminal_agents" "$OUT_DIR/samples/terminal_agents"
fi

# Sanity: the launcher + bundle + runtime are present.
for REQUIRED in sculptor_backend backend.cjs node; do
  if [[ ! -e "$OUT_DIR/$REQUIRED" ]]; then
    echo "ERROR: sidecar is missing $REQUIRED" >&2
    exit 1
  fi
done

echo "==> Sidecar built at $OUT_DIR"
