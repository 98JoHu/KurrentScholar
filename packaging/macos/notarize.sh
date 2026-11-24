#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 || ! -f "$1" || "$1" != *.dmg || -z "$2" ]]; then
  echo "Usage: bash packaging/macos/notarize.sh path/to/signed.dmg keychain-profile" >&2
  exit 2
fi

dmg="$1"
codesign --verify --strict --verbose=2 "$dmg"
xcrun notarytool submit "$dmg" --keychain-profile "$2" --wait
xcrun stapler staple "$dmg"
xcrun stapler validate "$dmg"
spctl --assess --type open --context context:primary-signature --verbose=2 "$dmg"
(cd "$(dirname "$dmg")" && shasum -a 256 "$(basename "$dmg")") > "${dmg%.dmg}.sha256"
