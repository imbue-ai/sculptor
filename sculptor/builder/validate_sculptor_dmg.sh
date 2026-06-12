#!/usr/bin/env bash
set -euo pipefail

DMG_PATH="${1}"
ARCH="${2}"

if [[ -z "${DMG_PATH}" || ! -f "${DMG_PATH}" ]]; then
  echo "ERROR: Provide the path to the DMG as the first argument." >&2
  exit 2
fi

if [[ -z "${ARCH}" ]]; then
  echo "ERROR: Provide the target architecture (e.g., x86_64) as the second argument." >&2
  exit 2
fi

# --- Minimal print helpers ---
ok()   { printf "[OK] %s\n" "$*"; }
warn() { printf "[WARN] %s\n" "$*"; }
fail() { printf "[FAIL] %s\n" "$*"; }
info() { printf "[INFO] %s\n" "$*"; }
rule() { printf "\n%s\n" "------------------------------------------------------------"; }

# --- Tool checks ---
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required tool: $1"
    echo "Install Xcode Command Line Tools (xcode-select --install) if needed." >&2
    exit 3
  fi
}
for t in xcrun codesign spctl hdiutil sed awk grep plutil; do need "$t"; done
PLISTBUDDY="/usr/libexec/PlistBuddy"
if [[ ! -x "$PLISTBUDDY" ]]; then
  fail "Missing PlistBuddy at $PLISTBUDDY"
  exit 3
fi

STAPLER="$(xcrun -f stapler)"
OTOOL="$(xcrun -f otool || true)"
LIPO="$(xcrun -f lipo || true)"
FILE_BIN="$(command -v file || true)"
if [[ -z "$OTOOL" || -z "$LIPO" || -z "$FILE_BIN" ]]; then
  fail "Missing developer tools (otool/lipo/file)."
  exit 3
fi

rule
echo "Verifying DMG and application..."
echo "DMG: $DMG_PATH"

# --- 1) DMG: notarization & policy (non-quarantine is acceptable) ---
rule
echo "1) DMG notarization & Gatekeeper"
DMG_OK=1

# Staple validation (preferred for notarized artifacts)
if "$STAPLER" validate "$DMG_PATH" >/tmp/staple_dmg.txt 2>&1; then
  ok "DMG stapler validate: OK"
else
  DMG_OK=0
  warn "DMG stapler validate: FAILED"
  sed 's/^/   /' /tmp/staple_dmg.txt || true
fi

# Gatekeeper policy check. Non-quarantined DMGs may not evaluate like recent downloads; warn only.
if spctl -a -vv -t open "$DMG_PATH" >/tmp/spctl_dmg.txt 2>&1; then
  ok "DMG spctl (open): OK"
else
  warn "DMG spctl (open): FAILED (file may not be quarantined; this is acceptable)"
  sed 's/^/   /' /tmp/spctl_dmg.txt || true
fi

# Signature (DMGs are often unsigned; informational only)
if codesign --verify --deep --verbose=4 "$DMG_PATH" >/tmp/codesign_dmg.txt 2>&1; then
  ok "DMG codesign verify: OK (image is signed)"
else
  info "DMG codesign verify: unsigned or not applicable"
  sed 's/^/   /' /tmp/codesign_dmg.txt | head -n 3 || true
fi

# --- 2) Mount DMG ---
rule
echo "2) Mount DMG read-only"
MOUNTPOINT=""
detach() {
  if [[ -n "${MOUNTPOINT}" && -d "${MOUNTPOINT}" ]]; then
    hdiutil detach "${MOUNTPOINT}" -quiet || true
  fi
}
trap detach EXIT

MOUNTPOINT="$(mktemp -d /tmp/verify_sculptor.XXXXXX)"
ATTACH_OUT="$(hdiutil attach -nobrowse -readonly -mountpoint "${MOUNTPOINT}" "$DMG_PATH" 2>&1 || true)"
if [[ ! -d "${MOUNTPOINT}" || -z "$(ls -A "${MOUNTPOINT}" 2>/dev/null)" ]]; then
  fail "Failed to mount DMG. Output:"
  echo "${ATTACH_OUT}"
  exit 4
fi
ok "Mounted at: ${MOUNTPOINT}"

# --- 3) Locate .app inside DMG ---
rule
echo "3) Locate .app inside DMG"
APP_PATH=""
if [[ -d "${MOUNTPOINT}/Sculptor.app" ]]; then
    APP_PATH="${MOUNTPOINT}/Sculptor.app"
else
    APP_PATH="$(find "${MOUNTPOINT}" -maxdepth 3 -type d -name "*.app" -print -quit || true)"
fi

if [[ -z "${APP_PATH}" || ! -d "${APP_PATH}" ]]; then
  fail "Could not find .app inside DMG."
  exit 5
fi
ok "Found app: ${APP_PATH}"

# --- 4) .app signature, hardened runtime, entitlements ---
rule
echo "4) .app signature & policy checks"
APP_OK=1

if "$STAPLER" validate "$APP_PATH" >/tmp/staple_app.txt 2>&1; then
  ok "App stapler validate: OK"
else
  APP_OK=0
  warn "App stapler validate: FAILED"
  sed 's/^/   /' /tmp/staple_app.txt || true
fi

if spctl -a -vv --type execute "$APP_PATH" >/tmp/spctl_app_exec.txt 2>&1; then
  ok "App spctl (execute): OK"
else
  APP_OK=0
  warn "App spctl (execute): FAILED"
  sed 's/^/   /' /tmp/spctl_app_exec.txt || true
fi

if codesign --verify --deep --strict --verbose=4 "$APP_PATH" >/tmp/codesign_app_verify.txt 2>&1; then
  ok "App codesign verify (deep/strict): OK"
else
  APP_OK=0
  warn "App codesign verify: FAILED"
  sed 's/^/   /' /tmp/codesign_app_verify.txt || true
fi

rule
echo "   - App signature details"
if codesign -dv --verbose=4 "$APP_PATH" >/tmp/codesign_app_dump.txt 2>&1; then
  TEAM_ID="$(grep -E 'TeamIdentifier=' /tmp/codesign_app_dump.txt | sed 's/.*TeamIdentifier=//')"
  IDENTITY="$(grep -E '^Authority=' /tmp/codesign_app_dump.txt | head -n1 | sed 's/^Authority=//' || echo '')"
  ok "TeamIdentifier: ${TEAM_ID:-unknown}"
  ok "Signing Identity (leaf): ${IDENTITY:-unknown}"
  if grep -q 'runtime' /tmp/codesign_app_dump.txt; then
    ok "Hardened Runtime: ENABLED"
  else
    warn "Hardened Runtime: NOT enabled"
    APP_OK=0
  fi
else
  APP_OK=0
  warn "Unable to dump codesign details for app."
fi

INFO_PLIST="${APP_PATH}/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
  BUNDLE_ID="$("$PLISTBUDDY" -c 'Print :CFBundleIdentifier' "$INFO_PLIST" 2>/dev/null || true)"
  if [[ -n "$BUNDLE_ID" ]]; then
    ok "Bundle Identifier: ${BUNDLE_ID}"
  else
    warn "Bundle Identifier not found in Info.plist"
  fi
else
  warn "Info.plist not found at: $INFO_PLIST"
fi

if codesign -d --entitlements :- "$APP_PATH" >/tmp/app_entitlements.plist 2>/dev/null; then
  ok "Entitlements (below)"
  sed 's/^/   /' /tmp/app_entitlements.plist
else
  info "No embedded entitlements found or not retrievable."
fi

[[ $APP_OK -eq 1 ]] || warn ".app checks reported issues."

# --- 5) Architecture & min macOS checks ---
rule
echo "5) Architecture & min macOS checks"
ARCH_OK=1


MAIN_EXE_NAME="$("$PLISTBUDDY" -c 'Print :CFBundleExecutable' "$INFO_PLIST" 2>/dev/null || true)"
MAIN_EXE_PATH="${APP_PATH}/Contents/MacOS/${MAIN_EXE_NAME:-}"
if [[ -n "$MAIN_EXE_NAME" && -f "$MAIN_EXE_PATH" ]]; then
  uv run builder validate-darwin-binary "$MAIN_EXE_PATH" $ARCH
else
  warn "Could not determine main executable from Info.plist; attempting to guess."
  GUESS_MAIN="$(find "${APP_PATH}/Contents/MacOS" -type f -perm +111 -maxdepth 1 2>/dev/null | head -n1 || true)"
  if [[ -n "$GUESS_MAIN" ]]; then
    uv run builder validate-darwin-binary "$GUESS_MAIN" $ARCH
  else
    warn "No executable found in Contents/MacOS"
    ARCH_OK=0
  fi
fi

uv run builder validate-darwin-binary "${APP_PATH}/Contents/Resources/sculptor_backend/sculptor_backend" $ARCH

# --- 6) Summary ---
rule
echo "SUMMARY"
EXIT=0
if [[ $DMG_OK -eq 1 ]]; then ok "DMG: notarization/spctl checks OK (non-quarantine allowed)"; else fail "DMG: issues found"; EXIT=1; fi
if [[ $APP_OK -eq 1 ]]; then ok ".app: signature, staple, hardened runtime OK"; else fail ".app: issues found"; EXIT=1; fi
if [[ $ARCH_OK -eq 1 ]]; then ok "Binaries: $ARCH and min macOS checks OK"; else fail "Binaries: issues found"; EXIT=1; fi

echo
if [[ $EXIT -eq 0 ]]; then
  ok "All checks passed."
else
  fail "One or more checks failed. See logs above."
fi

exit $EXIT
