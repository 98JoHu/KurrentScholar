# Development delivery record

Updated 2026-11-20 on the local Windows 11 development host. This is an engineering snapshot, not a
public release claim.

## Implemented

- Revision-pinned model catalog/download and local-only CPU TrOCR adapter, with safe per-project model
  provenance and model-change backups.
- Genuine generation transition-score extraction, line confidence, and truncation indication.
- PDF/image import, bounded incremental rendering, OpenCV fallback line detection, coordinates/order.
- Responsive two-panel Qt editor with overlays, background transcription, cancel, autosave, corrections,
  verification state, project reopen, and explicit nontechnical errors.
- Schema-versioned SQLite research records with document hash, provenance, immutable machine text,
  human text, confidence evidence, metadata storage, and correction history.
- TXT, DOCX, CSV, and JSON exporters; verified-line project CER/WER and confidence-band evaluation.
- English/German entry documentation, architecture, confidence, privacy, evaluation, methods,
  troubleshooting, publishing, citation, and third-party inventory.
- Reproducible dependency lock, CI, PyInstaller bundle, and Inno Setup installer/checksum workflow.

## Actual verification

- Ruff: passed.
- Regression suite: 41 passed, 1 opt-in real-model test skipped; the real-model test then passed
  separately against the newly installed recommended checkpoint.
- Both the source and packaged application loaded the new broad comparison model locally on CPU, generated
  text, and returned bounded token transition probabilities. A read-only low-confidence crop from the
  supplied manuscript also completed end to end; it is not accuracy ground truth.
- Source Qt offscreen startup: passed.
- PyInstaller Windows one-directory build: succeeded on Python 3.11.14.
- Packaged executable offscreen startup: exit 0. Packaged model installation/integrity verification and
  genuine CPU inference diagnostic: exit 0.
- Inno Setup 7.1.1 compile: succeeded (verified signed compiler, non-commercial use).
- The installer workflow previously passed a local install/start/uninstall cycle; the current corrected
  bundle passed packaged startup and model inference checks and still requires clean-VM acceptance.
- Installer size: 177,463,374 bytes.
- Installer SHA-256: `56ef024ea5da2d85c16d3915ba61551396970b85da20595ad1cac8573de19c9e`.

Artifact paths:

- `dist/installer/KurrentScholar-Setup-Windows-x64.exe`
- `dist/installer/SHA256SUMS.txt`
- `dist/KurrentScholar/`

Generated binaries are ignored by Git and must not be committed.

## Incomplete or unverified

- The broad comparison model was downloaded and real local CPU inference was executed with a synthetic
  architecture/score smoke input and one user-supplied manuscript crop. Reusable ground truth is still
  required for any accuracy claim and representative full-page evaluation.
- No clean Windows VM test, real scanned-PDF end-to-end test, model-download cancellation test,
  performance benchmark, confidence calibration, or installer code signing.
- Fallback segmentation is not validated for complex historical layout; manual geometry editing is absent.
- Runtime localization, thumbnails, settings/metadata UI, robust project relinking/packaging, pause/resume,
  word alignment, and advanced XML/PDF exports remain incomplete.
- Dependency notices are an inventory, not final legal review. Inno Setup was used under its displayed
  non-commercial terms; downstream build operators must review their own licensing context.
- macOS, Linux, and Android distributions are not built or tested.

## Maintainer inputs before publication

Name, optional ORCID, institution, repository URL, support/security contacts, software DOI, code-signing
identity, archival fixture licenses, and final release/version dates. Follow `docs/PUBLISHING.md` for GitHub,
release, checksum, clean-VM, and Zenodo steps.

