#!/usr/bin/env bash
# Build the Node sidecar that replaces the PyInstaller sculptor_backend.
#
# It produces, in $OUT_DIR (default sculptor/backend/dist/sculptor_backend),
# the same --onedir-style layout the Electron/Docker wrappers launch:
#
#   sculptor_backend/
#   ├── sculptor_backend        # launcher wrapper (sets env + execs node backend.cjs)
#   ├── backend.cjs             # the esbuild bundle (src/index.ts)
#   ├── node                    # pinned Node 24 runtime (the better-sqlite3 ABI)
#   ├── node_modules/           # the native addons (better-sqlite3, node-pty) + deps
#   ├── drizzle/                # schema migrations
#   └── frontend-dist/          # built UI (if present)
#
# Targets: macos-arm64 + linux-x64 only (REQ-COMPAT-001/002). On macOS the node
# binary + .node addons are codesigned when SIGN_IDENTITY is set (REQ-SEC-003).
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BACKEND_DIR"

# Pinned runtime. NOTE: the better-sqlite3 / node-pty prebuilt addons are built
# against Node 24's ABI (see the justfile's nvm pin), so the shipped runtime is
# Node 24, not the task doc's stale "20".
NODE_VERSION="${SIDECAR_NODE_VERSION:-24.17.0}"
BETTER_SQLITE3_VERSION="$(node -p "require('./package.json').dependencies['better-sqlite3']" 2>/dev/null || echo '11.8.1')"
NODE_PTY_VERSION="$(node -p "require('./package.json').dependencies['node-pty']" 2>/dev/null || echo '1.0.0')"

OUT_DIR="${OUT_DIR:-$BACKEND_DIR/dist/sculptor_backend}"
TARGET="${SIDECAR_TARGET:-host}" # host | macos-arm64 | linux-x64

# Map target -> nodejs.org dist slug.
node_dist_slug() {
  case "$1" in
    macos-arm64) echo "darwin-arm64" ;;
    linux-x64) echo "linux-x64" ;;
    host)
      local os
      os="$(uname -s)"
      [[ "$os" == "Darwin" ]] && echo "darwin-arm64" || echo "linux-x64"
      ;;
    *) echo "unsupported target: $1" >&2; exit 1 ;;
  esac
}

echo "==> Building esbuild bundle"
npm run build

echo "==> Staging sidecar at $OUT_DIR"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
cp dist/backend.cjs "$OUT_DIR/backend.cjs"
cp -R drizzle "$OUT_DIR/drizzle"

# The built UI (Task 1.4). The justfile copies it to sculptor/frontend-dist.
for CANDIDATE in "$BACKEND_DIR/../frontend-dist" "$BACKEND_DIR/../frontend/dist"; do
  if [[ -f "$CANDIDATE/index.html" ]]; then
    cp -R "$CANDIDATE" "$OUT_DIR/frontend-dist"
    break
  fi
done

echo "==> Installing native addons ($BETTER_SQLITE3_VERSION better-sqlite3, $NODE_PTY_VERSION node-pty)"
# A clean, minimal node_modules with only the native addons + their runtime deps,
# prebuilt for the target platform/ABI.
(
  cd "$OUT_DIR"
  npm init -y >/dev/null 2>&1
  npm install --omit=dev --no-audit --no-fund \
    "better-sqlite3@${BETTER_SQLITE3_VERSION}" "node-pty@${NODE_PTY_VERSION}" >/dev/null
  rm -f package.json package-lock.json
)

echo "==> Staging Node $NODE_VERSION runtime ($TARGET)"
SLUG="$(node_dist_slug "$TARGET")"
if [[ "$TARGET" == "host" && "$(node -v)" == "v${NODE_VERSION}" ]]; then
  # Local smoke build: reuse the running interpreter.
  cp "$(command -v node)" "$OUT_DIR/node"
else
  TARBALL="node-v${NODE_VERSION}-${SLUG}.tar.gz"
  URL="https://nodejs.org/dist/v${NODE_VERSION}/${TARBALL}"
  TMP="$(mktemp -d)"
  echo "    downloading $URL"
  curl -fsSL "$URL" -o "$TMP/$TARBALL"
  tar -xzf "$TMP/$TARBALL" -C "$TMP"
  cp "$TMP/node-v${NODE_VERSION}-${SLUG}/bin/node" "$OUT_DIR/node"
  rm -rf "$TMP"
fi
chmod +x "$OUT_DIR/node"

echo "==> Writing launcher"
cat > "$OUT_DIR/sculptor_backend" <<'LAUNCHER'
#!/usr/bin/env bash
# Sidecar launcher: run the bundled backend on the pinned Node, pointing it at
# the staged migrations + UI assets (cwd-independent). Forwards all args
# (--port, --host) and stdout (the ready line the wrappers scrape).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
export SCULPTOR_MIGRATIONS_DIR="${SCULPTOR_MIGRATIONS_DIR:-$HERE/drizzle}"
export SCULPTOR_STATIC_DIR="${SCULPTOR_STATIC_DIR:-$HERE/frontend-dist}"
export NODE_PATH="$HERE/node_modules"
exec "$HERE/node" "$HERE/backend.cjs" "$@"
LAUNCHER
chmod +x "$OUT_DIR/sculptor_backend"

# macOS: sign the runtime + native addons (REQ-SEC-003). Notarization happens in
# the packaging step (builder/darwin.py) on the final app bundle.
if [[ "$(uname -s)" == "Darwin" && -n "${SIGN_IDENTITY:-}" ]]; then
  echo "==> Codesigning node + native addons"
  codesign --force --options runtime --sign "$SIGN_IDENTITY" "$OUT_DIR/node"
  while IFS= read -r ADDON; do
    codesign --force --options runtime --sign "$SIGN_IDENTITY" "$ADDON"
  done < <(find "$OUT_DIR/node_modules" -name '*.node')
fi

echo "==> Sidecar built: $OUT_DIR"
