# Development delivery record

Recorded 2026-11-19 on the local Windows 11 development host. This is an engineering snapshot, not a
public release claim.

## Implemented

- Revision-pinned safe model manifest/download and local-only CPU TrOCR adapter.
- Genuine generation transition-score extraction, line confidence, and truncation indication.
- PDF/image import, bounded incremental rendering, OpenCV fallback line detection, coordinates/order.
- Responsive two-panel Qt editor with overlays, background transcription, cancel, autosave, corrections,
  verification state, project reopen, and explicit nontechnical errors.
- Schema-versioned SQLite research records with document hash, provenance, immutable machine text,
  human text, confidence evidence, metadata storage, and correction history.
- TXT, DOCX, CSV, and JSON exporters; CER/WER evaluation utility.
- English/German entry documentation, architecture, confidence, privacy, evaluation, methods,
  troubleshooting, publishing, citation, and third-party inventory.
- Reproducible dependency lock, CI, PyInstaller bundle, and Inno Setup installer/checksum workflow.

## Actual verification

- Ruff: passed.
- Pytest ordinary suite: 22 passed, 1 real-model test deselected.
- Real-model suite: 1 passed, 22 ordinary tests deselected; pinned model loaded locally on CPU,
  generated text, and returned bounded token transition probabilities in 9.62 seconds total test time.
- Consolidated suite with the pinned model enabled: 23 passed in 9.56 seconds; downloaded runtime model
  contained zero excluded pickle/training files.
- Source Qt offscreen startup: passed.
- PyInstaller Windows one-directory build: succeeded on Python 3.12.12.
- Packaged executable offscreen startup: exit 0.
- Inno Setup 7.1.1 compile: succeeded (verified signed compiler, non-commercial use).
- Installer local acceptance: install exit 0, installed-app smoke exit 0, uninstall exit 0, test directory removed.
- Installer size: 171,057,567 bytes.
- Installer SHA-256: `5c8ac99a18ef07dad98dded69eee8ffd99f6bb8490cea966872c5a096c6cf28c`.

Artifact paths:

- `dist/installer/KurrentScholar-Setup-Windows-x64.exe`
- `dist/installer/SHA256SUMS.txt`
- `dist/KurrentScholar/`

Generated binaries are ignored by Git and must not be committed.

## Incomplete or unverified

- The pinned 1.34 GB model was downloaded and real local CPU inference was executed, but only with a
  synthetic architecture/score smoke input. A legally reusable archival line/page and ground truth are
  still required for accuracy and full-page end-to-end evidence.
- No clean Windows VM test, real scanned-PDF end-to-end test, model-download UI integrity/cancellation test,
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

