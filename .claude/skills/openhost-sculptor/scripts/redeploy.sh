#!/bin/sh
# Redeploy an already-deployed app, KEEPING its persistent data (DB, workspaces,
# Claude auth, completed onboarding). Use to rebuild the same branch or switch to
# a different one.
#
# `oh app deploy` refuses an in-use name, so remove first — with --keep-data, so
# the persistent app_data survives. `oh app remove` blocks until the app is gone,
# so the deploy that follows can reuse the name immediately.
set -eu
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/_common.sh"

echo "Redeploying '$APP' at $REPO@$BRANCH (keeping data)..."
oh app remove "$APP" --keep-data
exec oh app deploy "$REPO@$BRANCH" --name "$APP" --grant-permissions-v2 --wait
