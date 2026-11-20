# Changelog

## 0.1.2-dev — unreleased

- Fixed the post-download UI hang by routing all background-worker completion, failure, status, and
  transcription progress signals through GUI-affine Qt slots instead of anonymous cross-thread callbacks.
- Added stage-by-stage model and transcription logging, Qt/thread exception capture, a native-fault log,
  and a GUI watchdog that records every thread stack if the event loop becomes unresponsive.
- Made download, integrity-check, and finalization phases explicit so completed downloads no longer appear
  stuck while the weights are being hashed.
- Replaced connected horizontal-band segmentation with line-centre and valley detection so descenders,
  flourishes, brackets, and underlining no longer merge many handwritten lines into one OCR crop.
- Added scanner-edge, footer-watermark, paper-shadow, bleed-through, and implausibly tall crop safeguards,
  validated across a 66-page historical manuscript at 300 DPI.
- Added safe re-segmentation: incompatible old results are never matched to new boxes by ordinal position;
  the UI creates a complete SQLite project backup before explicitly replacing segmentation and OCR output.

## 0.1.1-dev — unreleased

- Fixed installed-app model downloads with Windows trust-store support, explicit frozen-package
  dependencies, retries, persistent diagnostics, download progress, file-size validation, and a pinned
  safetensors SHA-256 integrity check.
- Added required first-launch model onboarding and packaged model self-diagnostics.
- Fixed ineffective cancellation, duplicate correction-history writes, project overwrite residue,
  unsafe retranscription replacement, PDF resource cleanup, stale project state, overlay scaling, and
  multi-page navigation.
- Removed broad uninstall-directory deletion and added the application license to installed files.
- Restored the PyInstaller recipe to version control and retained PyTorch namespaces required by frozen
  CPU inference.

## 0.1.0-dev — unreleased

- Initial offline-first desktop workflow, pinned line-level TrOCR adapter, fallback segmentation,
  SQLite projects, uncertainty evidence, four mandatory exports, tests, documentation, and Windows
  packaging automation.

