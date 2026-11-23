# macOS packaging

KurrentScholar is built natively for Apple Silicon and Intel; the two architectures are not combined
because the bundled PyTorch runtime makes a universal binary unnecessarily large. The GitHub workflow
creates signed, notarized, and stapled DMGs on native macOS runners.

Publishing requires these protected GitHub Actions secrets:

- `APPLE_CERTIFICATE_BASE64`: Developer ID Application certificate exported as a base64-encoded `.p12`.
- `APPLE_CERTIFICATE_PASSWORD`: password for that `.p12`.
- `APPLE_CODESIGN_IDENTITY`: full Developer ID Application identity.
- `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID`: notarization credentials.

The workflow fails before packaging if any credential is absent. This is intentional: do not distribute
an unnotarized replacement under the stable download names. macOS 12 or newer is the declared deployment
target; both DMGs still require clean-machine acceptance testing before a release is announced.

