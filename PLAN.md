# KurrentScholar implementation plan

Status date: 2026-11-20. This plan distinguishes implemented code from release claims. A checked
item means code exists; platform packaging is not considered verified until its artifact is built
and exercised in a clean virtual machine.

## Constraints and decisions

- The established default recognition model is `dh-unibe/trocr-kurrent` revision
  `2882072ac68f7aa09353a71092ebd5510f4b82cd`. The broader
  `dh-unibe/trocr-german-kurrent-xvi-xix-from-kurrent-v2` revision
  `bd1d96b67225b580846d7759f6ba74c66f56680e` is offered as an experimental comparison, not a claimed
  accuracy upgrade. Both are MIT line-image `VisionEncoderDecoderModel` checkpoints; full pages must
  never be sent to them.
- Only the safetensors checkpoint and runtime configuration/tokenizer files are downloaded. The
  redundant pickle checkpoints and training state are excluded. Each runtime set is approximately
  1.25 GiB / 1.34 GB decimal.
- Python 3.11 is the release baseline. Versions are pinned in `pyproject.toml` and the resolved
  environment is recorded in `uv.lock`.
- Kraken is not an initial hard dependency: its native Windows packaging and model distribution
  create avoidable release risk. Segmentation is behind an interface. The initial OpenCV projection
  backend is real and editable, but explicitly described as a fallback rather than research-grade
  layout analysis.
- Projects are SQLite files with schema versioning, immutable machine output, mutable corrected
  text, review state, annotations, settings, and provenance.

## Milestones and acceptance criteria

### M1 — technical foundation

- [x] Package structure and pinned model manifest.
- [x] Safe, revision-pinned model installation and local-only loading.
- [x] Line-only TrOCR inference with generation transition scores.
- [x] Documented line confidence aggregation and truncation warning.
- [x] Real-model CPU load/generation/transition-score smoke test executed with synthetic line input.
- [ ] Real-model accuracy/end-to-end test executed on a licensed archival fixture with provenance.

Acceptance: a supplied line crop can be recognized on CPU without network access after installation.

### M2 — document pipeline

- [x] Incremental PDF rendering and image import.
- [x] Page-range parser and rotation-aware rendering.
- [x] Replaceable segmentation protocol and OpenCV fallback.
- [x] Reading order and line crop preservation.
- [x] Incremental processing callback/cancellation contract.
- [ ] Add a validated historical-layout model backend.

Acceptance: a scanned page produces ordered line crops with source coordinates; failures remain visible.

### M3–M5 — desktop workflow, review, persistence, export

- [x] Native Qt welcome/main window, drag-and-drop, two-panel review, overlays, editing.
- [x] Background page processing, progress, cancellation, and incremental commits.
- [x] SQLite create/open/autosave/recovery-ready project format.
- [x] Confidence labels independent of human edits; verified status.
- [x] TXT, CSV, JSON, and DOCX exports with formula-injection-safe CSV.
- [ ] Interactive add/resize/reorder line geometry tools.
- [ ] Full bilingual string catalog and undo command stack.

Acceptance: users can import, transcribe, edit, save/reopen, and export without a terminal.

### M6 — Windows distribution

- [x] PyInstaller specification, Inno Setup script, and GitHub Actions build workflow.
- [x] Per-user installer configuration; model excluded from installer.
- [x] Local unsigned installer built, installed into an isolated path, app smoke-tested, and uninstalled.
- [ ] Build and smoke-test the installer on clean Windows (not possible without Python/Inno Setup
  on the target; the current local host is a development machine and CI/clean-VM evidence remains required).
- [ ] Code-signing certificate and signed release.

Acceptance: clean Windows VM install/start/uninstall test passes and the SHA-256 is published.

### M7–M8 — release quality and advanced formats

- [x] Architecture, confidence, privacy, evaluation, installation, and user documentation.
- [x] Unit tests for core calculations, storage, segmentation, and exports.
- [ ] Licensed end-to-end sample and measured performance/calibration results.
- [ ] PAGE XML, TEI, searchable PDF, macOS/Linux packages, alternate models.

Acceptance: dependency license audit and accessible bilingual workflow review are completed before 1.0.

## Release gates

1. No fabricated benchmark, screenshot, installer, signature, DOI, or download URL.
2. No document network transfer; only explicit model installation may use the network.
3. Clean-machine installer evidence and real-model line test are mandatory for a public stable release.
4. Maintainer must replace all publication placeholders in `CITATION.cff` and documentation.

