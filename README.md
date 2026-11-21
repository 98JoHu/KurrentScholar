# KurrentScholar

KurrentScholar is an offline-first desktop application for transcribing scanned historical German
Kurrent handwriting. It keeps manuscripts and research notes on your computer, shows detected source
lines beside editable transcriptions, and marks model uncertainty without presenting it as verified
accuracy.

> **No Python installation, programming knowledge, API key, account, or paid AI subscription is
> required for released installers.**

## Download

The project is **pre-release**. No tested public installer or genuine application screenshot exists yet;
do not treat the CI configuration as a release artifact. When the first Windows build passes clean-machine
acceptance testing, it will be linked from the repository's GitHub Releases page.

Planned first platform: Windows 10/11 x64, CPU-only, approximately 4 GB application storage plus a
separate one-time 1.34 GB model download. At least 8 GB RAM is the provisional development target, not
yet a measured published requirement.

## Intended workflow

1. Download and open the Windows installer from GitHub Releases.
2. Follow the ordinary per-user installation steps and launch KurrentScholar.
3. Confirm the one-time handwriting-model download (about 1.25 GiB at the pinned revision).
4. Open a historical PDF, PNG, JPEG, or TIFF and create a local research project.
5. Select **Transcribe**. The page is segmented into individual lines; only line crops reach TrOCR.
6. Compare source-line overlays with the editable text and review uncertain passages.
7. Save and reopen the SQLite project; export corrected or original machine text.

No manuscript is uploaded. Network access occurs only when the user starts model installation. The
default checkpoint is [dh-unibe/trocr-kurrent](https://huggingface.co/dh-unibe/trocr-kurrent), pinned
to commit `2882072ac68f7aa09353a71092ebd5510f4b82cd`; ordinary recognition then forces local-only
loading. Bern's newer broad 16th–19th-century checkpoint is available as an experimental comparison,
not as a claimed accuracy upgrade.

## Current functionality

- Incremental PDF/image rendering and ink-profile/valley line segmentation with source coordinates.
- Real local TrOCR inference using safetensors, CPU fallback, beam transition scores, and truncation flags.
- Native two-panel Qt review UI, background transcription, cancellation, autosave, line overlays, manual
  correction and verification.
- Schema-versioned SQLite projects preserving immutable machine output separately from edited text.
- A pinned model selector that prevents outputs from different checkpoints being mixed in one project;
  model changes require an automatic backup and clean retranscription.
- UTF-8 text, Word, formula-safe CSV, and provenance-rich JSON exports.
- CER/WER evaluation of human-verified project lines, plus confidence-band diagnostics; Windows
  build/installer workflow.

The included OpenCV segmenter is a packageable fallback for predominantly horizontal pages. It detects
line centres independently so descenders and flourishes do not create multi-line blocks, and can keep
spatially separated regions on the same row separate. It is not equivalent to a validated learned
historical-layout model and may still miss marginalia, complex columns, curves, tables, crossed text, or
decorative marks. Missed handwriting and confident recognition errors remain possible. Existing projects
made by an older detector can be migrated with **Re-segment**; KurrentScholar creates a separate backup
before replacing their derived boxes and transcriptions. See [the current plan](PLAN.md) before using this
pre-release software for research.

## Running from source (developers)

Install `uv`, then on Windows:

```powershell
uv sync --extra dev
uv run kurrentscholar
uv run pytest -m "not real_model"
```

The first model installation needs internet access. Real-model tests are opt-in and are never evidence
until their actual result is recorded. Build instructions are in [INSTALLATION.md](docs/INSTALLATION.md).

## Citation and acknowledgement

### Citing KurrentScholar

If you use KurrentScholar in research, cite the exact software release. Publication metadata in
`CITATION.cff` is intentionally placeholder-only until supplied by the maintainer.

### Citing the underlying recognition model

KurrentScholar uses independently developed TrOCR Kurrent models from Digital Humanities at the
University of Bern and its collaborators. KurrentScholar did not develop or train them. Cite the exact
model recorded in the project/export. The original model has a separate
[model DOI](https://doi.org/10.57967/hf/0442).

The upstream model card reports line-level results on its own nineteenth-century data and warns that the
model has not been extensively tested. Those figures must not be generalized to other scripts, periods,
page segmentation, or archival conditions.

## License

Original KurrentScholar code is MIT-licensed. Third-party components retain their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). A final bundled-binary license audit is a release gate.

