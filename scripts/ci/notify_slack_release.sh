#!/usr/bin/env bash
# Posts Slack notifications for Sculptor Desktop release pipeline events.
#
# Usage:
#   notify_slack_release.sh build-ready
#   notify_slack_release.sh released
#   notify_slack_release.sh dev-released
#   notify_slack_release.sh build-failed
#
# Required environment variables:
#   SLACK_WEBHOOK_URL       - Slack incoming webhook URL (from Vault)
#
# On GitHub Actions ($GITHUB_ACTIONS=true), derives the CI_* values from:
#   GITHUB_SERVER_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_SHA,
#   GITHUB_REF_TYPE, GITHUB_REF_NAME. When the repo is not
#   `imbue-ai/sculptor`, an EXPERIMENT marker is prepended so the
#   shared #sculptor-release channel knows to ignore the message.

set -euo pipefail

EVENT="${1:?Usage: notify_slack_release.sh <build-ready|released|dev-released|build-failed>}"

S3_RELEASES="https://imbue-sculptor-releases.s3.amazonaws.com"
S3_BUILDS="https://imbue-sculptor-builds.s3.amazonaws.com"

# Populate the normalised CI_* variables and host-specific URL templates from
# the GitHub Actions environment. The rest of the script reads only these vars.
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  : "${GITHUB_RUN_ID:?GITHUB_RUN_ID is unset}"
  : "${GITHUB_SERVER_URL:?GITHUB_SERVER_URL is unset}"
  : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is unset}"
  : "${GITHUB_SHA:?GITHUB_SHA is unset}"
  if [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    : "${GITHUB_REF_NAME:?GITHUB_REF_NAME is unset on a tag event}"
    CI_COMMIT_TAG="${GITHUB_REF_NAME}"
  fi
  CI_PROJECT_URL="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}"
  CI_PIPELINE_URL="${CI_PROJECT_URL}/actions/runs/${GITHUB_RUN_ID}"
  CI_COMMIT_SHA="${GITHUB_SHA}"
  CI_COMMIT_SHORT_SHA="${GITHUB_SHA:0:8}"
  COMMIT_URL="${CI_PROJECT_URL}/commit/${CI_COMMIT_SHA}"
  TAG_URL_FMT="${CI_PROJECT_URL}/releases/tag"
else
  echo "notify_slack_release.sh runs only in GitHub Actions (GITHUB_ACTIONS=true)." >&2
  exit 1
fi

if [ -n "${CI_COMMIT_TAG:-}" ]; then
  VERSION="${CI_COMMIT_TAG#sculptor-v}"
else
  # Dev builds: read the version that create-version-file wrote into pyproject.toml.
  VERSION=$(python3 -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('sculptor/pyproject.toml').read_text())
print(data['project']['version'])
")
fi

PIPELINE_URL="$CI_PIPELINE_URL"

# Build the version display: for tag builds, link to the tag; otherwise plain text.
if [ -n "${CI_COMMIT_TAG:-}" ]; then
  VERSION_DISPLAY="<${TAG_URL_FMT}/${CI_COMMIT_TAG}|${VERSION}>"
else
  VERSION_DISPLAY="${VERSION}"
fi

# Determine release channel and S3 prefix based on version type.
if echo "$VERSION" | grep -qE '\.dev'; then
  CHANNEL="DEV"
  RELEASE_PREFIX="slim-dev/${VERSION}"
elif echo "$VERSION" | grep -qE 'rc[0-9]'; then
  CHANNEL="LATEST"
  RELEASE_PREFIX="slim-rc"
else
  CHANNEL="STABLE (and LATEST)"
  RELEASE_PREFIX="slim"
fi

# Artifact links for the releases bucket (after publish-build-artifacts).
release_artifact_links() {
  echo "<${S3_RELEASES}/${RELEASE_PREFIX}/Sculptor-${VERSION}.dmg|DMG> · <${S3_RELEASES}/${RELEASE_PREFIX}/AppImage/x64/Sculptor-${VERSION}.AppImage|AppImage x64> · <${S3_RELEASES}/${RELEASE_PREFIX}/AppImage/arm64/Sculptor-${VERSION}.AppImage|AppImage arm64>"
}

# Artifact links for the builds bucket (before publish-build-artifacts, keyed by SHA).
build_artifact_links() {
  local prefix="${S3_BUILDS}/slim/${CI_COMMIT_SHA}"
  echo "<${prefix}/Sculptor.dmg|DMG> · <${prefix}/AppImage/x64/Sculptor.AppImage|AppImage x64> · <${prefix}/AppImage/arm64/Sculptor.AppImage|AppImage arm64>"
}

case "$EVENT" in
  build-ready)
    TEXT=":package: *Sculptor ${VERSION_DISPLAY}* build is ready for release to ${CHANNEL}"
    TEXT="${TEXT}\n<${COMMIT_URL}|\`${CI_COMMIT_SHORT_SHA}\`> · <${PIPELINE_URL}|Pipeline>"
    TEXT="${TEXT}\n$(build_artifact_links)"
    TEXT="${TEXT}\n\nTo publish, trigger the <${PIPELINE_URL}|release job> in the pipeline."
    ;;
  released)
    TEXT=":rocket: *Sculptor ${VERSION_DISPLAY}* has been released to ${CHANNEL}"
    TEXT="${TEXT}\n<${COMMIT_URL}|\`${CI_COMMIT_SHORT_SHA}\`> · <${PIPELINE_URL}|Pipeline>"
    TEXT="${TEXT}\n$(release_artifact_links)"
    ;;
  dev-released)
    TEXT=":wrench: *Dev Sculptor ${VERSION_DISPLAY}* has been published"
    TEXT="${TEXT}\n<${COMMIT_URL}|\`${CI_COMMIT_SHORT_SHA}\`> · <${PIPELINE_URL}|Pipeline>"
    TEXT="${TEXT}\n$(release_artifact_links)"
    ;;
  build-failed)
    TEXT=":x: *Sculptor ${VERSION_DISPLAY}* build failed"
    TEXT="${TEXT}\n<${COMMIT_URL}|\`${CI_COMMIT_SHORT_SHA}\`> · <${PIPELINE_URL}|Pipeline>"
    ;;
  *)
    echo "Unknown event: $EVENT (expected build-ready, released, dev-released, or build-failed)" >&2
    exit 1
    ;;
esac

# When running outside the real-publishing repo, loudly mark the message so the
# shared release channel doesn't treat it as a real release. The
# real-publishing repo matches the PUBLISH_DRY_RUN whitelist in
# .github/workflows/build-desktop.yml.
case "${GITHUB_REPOSITORY:-}" in
  imbue-ai/sculptor) IS_REAL_PUBLISH_REPO=true ;;
  *) IS_REAL_PUBLISH_REPO=false ;;
esac
if [ "${GITHUB_ACTIONS:-}" = "true" ] && [ "${IS_REAL_PUBLISH_REPO}" != "true" ]; then
  TEXT=":test_tube: *EXPERIMENT — practice-repo dry-run from ${GITHUB_REPOSITORY}. Ignore this message.* :test_tube:\n${TEXT}"
fi

BODY=$(cat <<EOF
{
  "blocks": [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "${TEXT}"
      }
    }
  ]
}
EOF
)

RESPONSE_FILE="$(mktemp)"
HTTP_STATUS=$(curl -sS -w '%{http_code}' -o "$RESPONSE_FILE" \
  -X POST -H 'Content-Type: application/json' \
  -d "$BODY" \
  "$SLACK_WEBHOOK_URL")

if [ "$HTTP_STATUS" = "200" ]; then
  echo "Slack notification sent (${EVENT})"
else
  echo "Warning: Slack notification failed (HTTP ${HTTP_STATUS})" >&2
  cat "$RESPONSE_FILE" >&2 || true
  # Non-fatal: don't fail the pipeline over a notification.
fi

rm -f "$RESPONSE_FILE"
