#!/usr/bin/env bash
# Regenerates the committed PWA icons in public/ from public/favicon.svg.
# Run after changing favicon.svg: `pnpm run generate-pwa-icons`.
# Requires ImageMagick 7 (`brew install imagemagick`).
#
# The SVG's native size is 336px at 96dpi, so each target size gets a
# -density of ceil(96 * target / 336) to rasterize at full resolution
# (a plain -resize would render at 336px and upscale, coming out blurry).
set -euo pipefail

cd "$(dirname "$0")/../public"

SVG=favicon.svg
# The SVG's own background color; used to pad the maskable icon and to
# flatten the iOS icon (iOS renders icon transparency as black).
CREAM="#f2f0e7"

# Manifest icons (purpose "any"): full-bleed rasters of the SVG.
magick -density 147 -background none "$SVG" -resize 512x512 -depth 8 -strip pwa-512x512.png
magick -density 55 -background none "$SVG" -resize 192x192 -depth 8 -strip pwa-192x192.png

# Maskable icon: glyph shrunk to 80% (the maskable safe zone) and centered
# on a full-bleed background, so circular launcher masks don't clip it.
magick -density 118 -background none "$SVG" -resize 410x410 \
  -gravity center -background "$CREAM" -extent 512x512 -depth 8 -strip \
  pwa-maskable-512x512.png

# iOS Add to Home Screen icon (referenced from index.html): opaque.
magick -density 52 -background "$CREAM" "$SVG" -resize 180x180 -alpha off -depth 8 -strip \
  apple-touch-icon.png

echo "Regenerated: pwa-512x512.png pwa-192x192.png pwa-maskable-512x512.png apple-touch-icon.png"
