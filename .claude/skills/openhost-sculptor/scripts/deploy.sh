#!/bin/sh
# Fresh deploy of the Sculptor OpenHost app (app name not yet in use).
#
# Builds from source at $REPO@$BRANCH — takes ~10 min (--wait blocks until done).
# For an app that already exists, use redeploy.sh (keep data) or reset.sh (wipe).
set -eu
APP=sculptor
REPO=https://github.com/imbue-ai/sculptor
BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Deploying $REPO@$BRANCH as app '$APP' (~10 min build)..."
exec oh app deploy "$REPO@$BRANCH" --name "$APP" --wait
