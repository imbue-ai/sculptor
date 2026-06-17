# shellcheck shell=sh
# Shared bootstrap for the openhost-sculptor deploy/reset scripts.
#
# Not run directly — each script sources it after setting SCRIPT_DIR to its own
# folder. Everything is auto-derived (no config file); the four values below are
# exported for the scripts that source this file (and the oh/git subprocesses):
#   APP    - OpenHost app name      (openhost.toml [app].name)
#   REPO   - GitHub repo to build   (the origin remote, normalized to an https URL)
#   BRANCH - branch to deploy       (the repo's current branch)
#   HOST   - public URL host        (APP under the default oh instance's domain;
#                                     verify.sh only — left unset if oh can't tell us)

SKILL_DIR=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
REPO_ROOT=$(git -C "$SKILL_DIR" rev-parse --show-toplevel)

# APP: the [app].name from the app manifest at the repo root. Piped through head
# so a missing file yields an empty APP (caught below) rather than a sed error.
APP=$(sed -n 's/^[[:space:]]*name[[:space:]]*=[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$REPO_ROOT/openhost.toml" | head -n 1)
: "${APP:?could not read [app].name from $REPO_ROOT/openhost.toml}"

# REPO: the origin remote, normalized git@github.com:org/repo(.git) -> https URL.
ORIGIN_URL=$(git -C "$SKILL_DIR" remote get-url origin)
case "$ORIGIN_URL" in
    git@*:*) REPO="https://github.com/${ORIGIN_URL#*:}" ;;
    *) REPO="$ORIGIN_URL" ;;
esac
REPO=${REPO%.git}

# BRANCH: the repo's current branch (resolved from the skill folder, so it's
# correct regardless of where the script is invoked from).
BRANCH=$(git -C "$SKILL_DIR" rev-parse --abbrev-ref HEAD)

export APP REPO BRANCH

# HOST: APP under the default oh instance's domain, e.g. sculptor.<zone-domain>.
# Best-effort and verify.sh-only: left unset if the oh CLI can't tell us, so
# verify.sh's guard fires with a clear message. Keep this the last statement so
# the missing-HOST case still leaves a 0 exit status for the sourcing script.
ZONE=$(oh instance list 2>/dev/null | awk '/\[default\]/ { print $1; exit }')
if [ -n "$ZONE" ]; then
    export HOST="$APP.$ZONE"
fi
