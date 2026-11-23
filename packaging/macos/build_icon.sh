#!/usr/bin/env bash
set -euo pipefail

source_png="${1:-assets/branding/kurrentscholar-logo-readme.png}"
output_icns="${2:-assets/branding/kurrentscholar.icns}"
iconset="$(mktemp -d)/KurrentScholar.iconset"
mkdir -p "$iconset"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$source_png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$source_png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$iconset" -o "$output_icns"
