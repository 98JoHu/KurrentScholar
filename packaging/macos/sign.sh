#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! -d "$1/Contents/Frameworks" ]]; then
  echo "Usage: APPLE_CODESIGN_IDENTITY=... bash packaging/macos/sign.sh path/to/app" >&2
  exit 2
fi
: "${APPLE_CODESIGN_IDENTITY:?Set a Developer ID Application identity}"
app="$1"

# PyInstaller signs Mach-O files; framework resources also need a bundle signature.
while IFS= read -r -d '' framework; do
  codesign --force --options runtime --timestamp --sign "$APPLE_CODESIGN_IDENTITY" "$framework"
done < <(find "$app/Contents/Frameworks" -depth -type d -name '*.framework' -print0)
codesign --force --options runtime --timestamp --sign "$APPLE_CODESIGN_IDENTITY" "$app"
codesign --verify --deep --strict "$app"
