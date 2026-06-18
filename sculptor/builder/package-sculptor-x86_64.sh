#!/usr/bin/env bash
# shellcheck shell=bash
# This module exists to package sculptor for Intel Macs on Apple Silicon hosts.
set -Eeuo pipefail
IFS=$'\n\t'

# --- Constants ---------------------------------------------------------------
ARCH="x86_64"
X64_BASH="/usr/local/bin/bash"
[[ -x "$X64_BASH" ]] || X64_BASH="/bin/bash"

SOURCE_DIR="$(pwd)"
WORKTREE="../../../sculptor-${ARCH}"
FRONTEND_DIR="${WORKTREE}/sculptor/frontend"
NVM_DIR_X64="$HOME/.nvm-x64"
NODE_VERSION="v20.13.1"   # keep exactly as your .nvmrc
ELECTRON_ARCH="x64"

# --- Functions ---------------------------------------------------------------

enter_rosetta_bash() {
  if [[ "$(uname -m)" != "x86_64" ]]; then
    # Re-exec this script in an x86_64 bash via Rosetta
    exec arch -x86_64 "$X64_BASH" -l "$0" "$@"
  fi
}

init_homebrew_env() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if [[ "$(uname -m)" == "arm64" ]]; then
      # Running on Apple Silicon host (but we are in an x64 shell now)
      if [[ -x /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
      fi
    else
      if [[ -x /usr/local/bin/brew ]]; then
        eval "$(/usr/local/bin/brew shellenv)"
      fi
    fi
  fi
}

# Prefer Intel Homebrew toolchain; strip /opt/homebrew from PATH
prefer_intel_path() {
  local clean_path
  clean_path="$(printf "%s" "${PATH:-}" | awk -v RS=: -v ORS=: '$0 !~ /^\/opt\/homebrew/ {print}')"
  clean_path="${clean_path%:}"
  export PATH="/usr/local/bin:/usr/local/sbin:${clean_path}"
}

require_nvm_intel() {
  # Use a dedicated NVM dir for x64 so it never collides with ARM installs
  export NVM_DIR="$NVM_DIR_X64"
  mkdir -p "$NVM_DIR"

  ibrew install nvm

  # Temporarily relax strict mode; nvm is not fully -e/-u safe when .nvmrc
  # points to a not-yet-installed version. See nvm issues/1985 and 1587.
  set +eu
  if [ -s "/usr/local/opt/nvm/nvm.sh" ]; then
    . "/usr/local/opt/nvm/nvm.sh" --no-use
  else
    echo "nvm.sh not found at /usr/local/opt/nvm/nvm.sh (Intel Homebrew). Did 'arch -x86_64 brew install nvm' run?" >&2
    exit 1
  fi
  set -eu
}

ensure_node_installed() {
  # Install the exact version our project requires
  set +e
  nvm ls "$NODE_VERSION" >/dev/null 2>&1
  local had_version=$?
  set -e
  if [[ $had_version -ne 0 ]]; then
    # Still relax strict mode during install to avoid exit 3 on .nvmrc
    set +eu
    nvm install "$NODE_VERSION"
    set -eu
  fi
}

npm_with_node() {
  # Run npm under the requested Node via nvm exec (keeps env isolation)
  nvm exec "$NODE_VERSION" npm "$@"
}

verify_node_arch_x64() {
  local node_path
  node_path="$(nvm which "$NODE_VERSION")"
  file "$node_path"
  if ! file "$node_path" | grep -q "x86_64"; then
    echo "ERROR: node at $node_path is not x86_64!" >&2
    exit 1
  fi
  if ! nvm exec "$NODE_VERSION" node -p "process.arch" | grep -q "^x64$"; then
    echo "ERROR: node process is not x64!" >&2
    exit 1
  fi
}

verify_node_arch_arm64() {
  local node_path
  node_path="$(nvm which "$NODE_VERSION")"
  file "$node_path"
  if ! file "$node_path" | grep -q "arm64"; then
    echo "ERROR: node at $node_path is not arm64!" >&2
    exit 1
  fi
  if ! nvm exec "$NODE_VERSION" node -p "process.arch" | grep -q "^arm64$"; then
    echo "ERROR: node process is not arm64!" >&2
    exit 1
  fi
}

make_worktree_and_stage_assets() {
  (git worktree remove -f "$WORKTREE" 2>/dev/null || true)
  git worktree prune -v
  # Finally delete the directory
  (rm -rf "$WORKTREE" || true)
  git worktree add -f "$WORKTREE" HEAD

  # copy your dist/config artifacts
  mkdir -p "${WORKTREE}/sculptor/dist"
  cp -R dist/ "${WORKTREE}/sculptor/dist/" || true

  mkdir -p "${WORKTREE}/sculptor/frontend/config"
  cp frontend/config/* "${WORKTREE}/sculptor/frontend/config/"
}

build_frontend_app() (
  # Let's make sure the caches are clean
  rm -rf .node_modules/.cache ~/.cache/electron ~/.cache/electron-builder 2>/dev/null || true

  # Install JS deps
  npm_with_node ci

  # Backend & assets
  just sidecar "cpython-3.11.13-macos-x86_64-none"
  ARCH=$ARCH just electron-assets

  # Build via Electron Forge (darwin x64)
  # Keep your env exports; pass explicit arch/platform to be crystal clear.
  export npm_config_arch="$ELECTRON_ARCH"
  export npm_config_target_arch="$ELECTRON_ARCH"
  export ELECTRON_ARCH="$ELECTRON_ARCH"

  # Your existing "uv" environment vars step; preserve exact semantics
  # (eval ensures npm sees the variables in this subshell)
  eval "$(uv run --project sculptor builder setup-build-vars production)"


  # <REPLACEMENT> begins here. We want to run:
  # `nvm exec "$NODE_VERSION" npm run electron:make -- -- --platform=darwin --arch=x64`
  # But there is a bug which prevents the right electron from being run in the right arch mode!

  # Actual exec of the electron:make command; Note we don't call pre/post inside here.
  nvm exec v20.13.1 -- npx --no-install electron-forge package \
     --platform=darwin \
     --arch=x64

  # </REPLACEMENT>
)

copy_outputs_and_verify() {
  # Versioned DMG name
  set -x
  local version dmg outdir zipdir

  # Unclear why, but uv run builder version is returning non-zero sometimes
  version="$(cd $SOURCE_DIR && uv run --project sculptor builder version | head -n1 | cut -f2 -d' ')" || true
  dmg="out/make/Sculptor.dmg"

  outdir="$SOURCE_DIR/../dist"
  zipdir="$outdir/zip"

  mkdir -p "$outdir" "$zipdir"
  # Rename DMG with version and arch
  cp "$dmg" "$outdir/Sculptor-${version}-${ARCH}.dmg"
  # And also just with the Arch (for the "latest")
  cp "$dmg" "$outdir/Sculptor-${ARCH}.dmg"

  # Copy the ZIP artifacts out
  if [[ -d out/make/zip ]]; then
    cp -R out/make/zip/* "$zipdir"/
  fi
}

# --- Main --------------------------------------------------------------------
enter_rosetta_bash "$@"
init_homebrew_env
prefer_intel_path

# Force Intel brew via helpers (keep your helpers if you want)
abrew() { /opt/homebrew/bin/brew "$@"; }
ibrew() { arch -"$ARCH" /usr/local/bin/brew "$@"; }

make_worktree_and_stage_assets

# Run the Intel build inside FRONTEND_DIR with isolated x64 NVM/Node
(
  cd "$FRONTEND_DIR"
  require_nvm_intel
  ensure_node_installed
  verify_node_arch_x64

  # First, we need to manually trigger `pre electron make` to ensure that the correct version is seen by electron
  nvm exec v20.13.1 -- npm run preelectron:package

  build_frontend_app
  echo "App was built, on to package"

  arch -arm64 /usr/bin/env -i \
      HOME="$HOME" \
      FRONTEND_DIR="$PWD" \
      NVM_DIR="$HOME/.nvm" \
      PATH="/usr/local/bin:/usr/local/sbin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin" \
      ${SKIP_NOTARIZE_AND_SIGN:+SKIP_NOTARIZE_AND_SIGN="$SKIP_NOTARIZE_AND_SIGN"} \
      /bin/bash --noprofile --norc -lc '
        set -Eeuo pipefail
        abrew() { /opt/homebrew/bin/brew "$@"; }
        abrew install nvm

        # Use native ARM Homebrew nvm
        if [ -s "/opt/homebrew/opt/nvm/nvm.sh" ]; then
          . "/opt/homebrew/opt/nvm/nvm.sh"
        else
          echo "ARM nvm not found at /opt/homebrew/opt/nvm/nvm.sh" >&2; exit 1
        fi

        # We are incrementing to build with the next Node version here so it will not conflict with the other
        # version we have.
        NODE_VERSION="v20.14.0"

        nvm install $NODE_VERSION
        nvm use $NODE_VERSION

        set -x


        node_path="$(nvm which "$NODE_VERSION")"
        file "$node_path"
        if ! file "$node_path" | grep -q "arm64"; then
          echo "ERROR: node at $node_path is not arm64!" >&2
          exit 1
        fi

        if ! nvm exec "$NODE_VERSION" node -p "process.arch" | grep -q "^arm64$"; then
          echo "ERROR: node process is not arm64!" >&2
          exit 1
        fi

        # Let us nuke the old node_modules and get new ones
        rm -rf node_modules
        npm ci --foreground-scripts

        npx --no-install electron-forge make \
          --platform=darwin \
          --arch=x64 \
          --skip-package \
          --targets=@electron-forge/maker-dmg,@electron-forge/maker-zip

        rm -rf node_modules'

    set -uexo pipefail
    copy_outputs_and_verify
)
