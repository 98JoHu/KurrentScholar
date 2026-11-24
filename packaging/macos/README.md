# macOS packaging

KurrentScholar is built natively for Apple Silicon and Intel; the two architectures are not combined
because the bundled PyTorch runtime makes a universal binary unnecessarily large. The GitHub workflow
creates signed, notarized, and stapled DMGs on native macOS runners on every push to `main`,
for `v*` tags, or manually through Actions. Main-branch builds are downloadable Actions artifacts;
version tags also attach the DMGs to a GitHub Release, independently of the Windows build.
Intel uses PyTorch 2.2.2, the last version with Intel macOS wheels; other platforms keep 2.5.1.

Publishing requires these protected GitHub Actions secrets:

- `APPLE_CERTIFICATE_BASE64`: Developer ID Application certificate exported as a base64-encoded `.p12`.
- `APPLE_CERTIFICATE_PASSWORD`: password for that `.p12`.
- `APPLE_CODESIGN_IDENTITY`: full Developer ID Application identity.
- `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID`: notarization credentials.

The workflow fails before packaging if any credential is absent. This is intentional: do not distribute
an unnotarized replacement under the stable download names. macOS 12 or newer is the declared deployment
target; both DMGs still require clean-machine acceptance testing before a release is announced.


## One-time GitHub setup

A repository administrator must add the secrets above under Settings → Secrets and variables →
Actions. Export only the intended **Developer ID Application** certificate and its matching private
key from Keychain Access as a password-protected `.p12`. Base64-encode that file for
`APPLE_CERTIFICATE_BASE64`; never commit the certificate, private key, or passwords.
`APPLE_CODESIGN_IDENTITY` can be the certificate SHA-1 fingerprint, which avoids ambiguity when
multiple certificates have the same display name. The certificate's team must match `APPLE_TEAM_ID`.
Create an app-specific password for the signing Apple ID at https://account.apple.com/.

Signing credentials are available to workflow code on `main`; protect that branch and review workflow
changes. No credentials are used for pull-request tests. No Xcode Cloud connection is necessary.
The existing GitHub account must have Actions enabled and allow the macOS runner labels used here.

## Local build and notarization

On a Mac of the target architecture, with Python 3.11 and uv installed:

```bash
uv sync --extra dev --frozen
bash packaging/macos/build_icon.sh
export APPLE_CODESIGN_IDENTITY="<Developer ID Application certificate SHA-1>"
uv run pyinstaller packaging/macos/KurrentScholar.spec --noconfirm --clean
dist/KurrentScholar.app/Contents/MacOS/KurrentScholar --smoke-test
codesign --verify --deep --strict --verbose=2 dist/KurrentScholar.app
```

PyInstaller signs the nested binaries with the selected identity during collection. Avoid re-signing
only the outer bundle after packaging. To finish an already signed DMG, first store notarization
credentials on your Mac (the command prompts for your app-specific password; do not put it in chat):

```bash
xcrun notarytool store-credentials KurrentScholar --apple-id "<your Apple ID>" --team-id "<certificate team ID>"
bash packaging/macos/notarize.sh "/absolute/path/to/KurrentScholar-macOS-Apple-Silicon.dmg" KurrentScholar
bash packaging/macos/notarize.sh "/absolute/path/to/KurrentScholar-macOS-Intel.dmg" KurrentScholar
```

A signed DMG without notarization is a local build, not a completed public release. Notarization and
stapling modify the DMG, so regenerate checksums afterwards (the helper does this automatically).
