#!/bin/sh
# Full reset: wipe ALL persistent data (DB, workspaces, Claude auth, onboarding
# state) and redeploy a fresh-onboarding instance. CLI-only — no SSH.
#
# `oh app remove` WITHOUT --keep-data deletes the persistent app_data, then the
# deploy rebuilds from source (~10 min). To keep data instead, use redeploy.sh.
set -eu
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/_common.sh"

printf 'This WIPES all data for app "%s" and redeploys fresh. Continue? [y/N] ' "$APP"
read -r reply
case "$reply" in
    [yY] | [yY][eE][sS]) ;;
    *)
        echo "Aborted."
        exit 1
        ;;
esac

echo "Removing '$APP' (full data wipe)..."
oh app remove "$APP" # no --keep-data: deletes persistent app_data
echo "Deploying fresh $REPO@$BRANCH as '$APP' (~10 min build)..."
exec oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
