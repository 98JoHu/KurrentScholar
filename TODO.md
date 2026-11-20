# Progress tracker

## Before the first public release

- [x] Run `pytest -m real_model` after the pinned model is installed (synthetic architecture/score smoke).
- [ ] Repeat real-model evaluation with a licensed archival line and ground truth.
- [ ] Select a legally reusable Kurrent page/ground truth and record provenance/license.
- [ ] Validate segmentation on representative archival layouts; integrate a stronger backend.
- [ ] Execute the Windows CI release job and repeat the successful local install/start/uninstall smoke test
  in a clean Windows x64 VM without Python or development tools.
- [ ] Capture screenshots only from the verified application build.
- [ ] Complete keyboard/screen-reader review and German translation coverage.
- [ ] Run a complete binary dependency and Qt LGPL compliance audit.
- [ ] Fill maintainer name, ORCID, institution, repository URL, and release DOI.
- [ ] Benchmark CPU speed/memory on named hardware; do not publish estimates until measured.
- [ ] Add interactive line-boundary editing and correction-history UI.
- [ ] Add byte-level model download progress and safe in-flight cancellation (current download is
  resumable and runs off the UI thread; the dialog can be hidden but not abort the active HTTP request).

## Later

- [ ] Kraken or validated learned segmentation backend.
- [ ] PAGE XML and TEI subsets with schema validation.
- [ ] Searchable PDF export.
- [ ] macOS notarized bundle and Linux AppImage.
- [ ] Confidence calibration using disjoint calibration/test sets.

