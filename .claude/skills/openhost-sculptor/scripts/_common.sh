# Shared bootstrap for the openhost-sculptor deploy/reset scripts.
#
# Not run directly — each script sources it after setting SCRIPT_DIR to its own
# folder. Loads the gitignored instance config (openhost.env) and derives:
#   APP    - OpenHost app name              (required; from openhost.env)
#   REPO   - GitHub repo the deploy builds  (required; from openhost.env)
#   HOST   - public URL host for verify     (from openhost.env; verify.sh only)
#   BRANCH - branch to deploy               (openhost.env, else current branch)

SKILL_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$SKILL_DIR/openhost.env"

if [ ! -f "$ENV_FILE" ]; then
    echo "error: $ENV_FILE not found." >&2
    echo "Copy openhost.env.example to openhost.env (same folder) and fill it in." >&2
    exit 1
fi

set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

: "${APP:?set APP in openhost.env}"
: "${REPO:?set REPO in openhost.env}"
# Default the branch to the repo's current branch (resolved from the skill
# folder, so it's correct regardless of where the script is invoked from).
: "${BRANCH:=$(git -C "$SKILL_DIR" rev-parse --abbrev-ref HEAD)}"
