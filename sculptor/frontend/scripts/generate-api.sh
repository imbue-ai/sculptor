#!/usr/bin/env bash
# Emit the OpenAPI schema and re-run codegen only when any input changed.
# Inputs are: the schema, the openapi-ts config, the js-types fixup script,
# this script itself, and the pinned @hey-api/openapi-ts version.
set -euo pipefail

cd "$(dirname "$0")/.."

digest_file="node_modules/.cache/sculptor-codegen-digest"
mkdir -p "$(dirname "$digest_file")"

compute_digest() {
  {
    cat sculptor_schema.json
    cat openapi-ts.config.ts
    cat ../../sculptor/sculptor/scripts/fixup_js_types.py
    cat scripts/generate-api.sh
    grep '@hey-api/openapi-ts' package.json || true
  } | shasum | awk '{print $1}'
}

npm run generate-api-json-schema

new_digest=$(compute_digest)

# Files openapi-ts is expected to produce. If any are missing we must
# regenerate even when the digest matches, otherwise a partially-deleted
# src/api/ would silently stay broken.
expected_outputs=(
  src/api/types.gen.ts
  src/api/sdk.gen.ts
  src/api/client.gen.ts
  src/api/index.ts
)

all_outputs_present=true
for f in "${expected_outputs[@]}"; do
  if [ ! -f "$f" ]; then
    all_outputs_present=false
    break
  fi
done

if [ -f "$digest_file" ] \
    && [ "$all_outputs_present" = true ] \
    && [ "$new_digest" = "$(cat "$digest_file")" ]; then
  echo "Codegen inputs unchanged, skipping openapi-ts codegen."
  exit 0
fi

npx @hey-api/openapi-ts
npm run fixup-js-types
echo "$new_digest" > "$digest_file"
