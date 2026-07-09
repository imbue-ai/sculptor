#!/usr/bin/env bash
# Roll up the extension SDK's public declarations into a single .d.ts shipped
# inside the build-sculptor-extension skill. The skill travels with the app to
# agents in any repo, so the rolled-up file is their authoritative typed
# contract — and because it is checked in, a PR that changes the SDK surface
# shows the contract diff for review.
#
# Usage: generate-extension-sdk-dts.sh [out-file]
# The default out-file is the skill's sdk.d.ts; the freshness check passes a
# temp path and diffs.
set -euo pipefail

cd "$(dirname "$0")/.."

out_file="${1:-../sculptor-plugin/skills/build-sculptor-extension/sdk.d.ts}"

if [ ! -f src/api/types.gen.ts ]; then
  echo "src/api/types.gen.ts is missing - run 'just generate-api' first." >&2
  exit 1
fi

tmp_file=$(mktemp)
trap 'rm -f "$tmp_file"' EXIT

# --no-check: the rollup imports host-provided externals (react, lucide-react)
# and lands outside the frontend package, so the bundler's post-emit typecheck
# cannot resolve them there; the input program is already typechecked.
pnpm exec dts-bundle-generator \
  --project tsconfig.extension-sdk-dts.json \
  --no-check \
  --no-banner \
  --export-referenced-types \
  --out-file "$tmp_file" \
  src/extensions/sdk/index.ts >/dev/null

{
  echo "// GENERATED FILE - do not edit. Regenerate with: just generate-extension-sdk-dts"
  echo "// The public contract of \"@sculptor/extension-sdk\" (host SDK major 1), rolled up"
  echo "// from sculptor/frontend/src/extensions/sdk/ in the Sculptor repo."
  cat "$tmp_file"
} > "$out_file"

echo "Done: $out_file"
