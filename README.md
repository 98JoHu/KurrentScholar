<p align="center">
  <img src="assets/branding/kurrentscholar-logo-readme.png" alt="KurrentScholar logo" width="180">
</p>

<h1 align="center">KurrentScholar</h1>

<p align="center">
  Private, local transcription and review of historical German Kurrent manuscripts.
</p>

<p align="center">
  <a href="https://github.com/98JoHu/KurrentScholar/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/98JoHu/KurrentScholar"></a>
  <a href="https://github.com/98JoHu/KurrentScholar/actions/workflows/ci.yml"><img alt="Tests" src="https://github.com/98JoHu/KurrentScholar/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="MIT license" src="https://img.shields.io/badge/license-MIT-bc8e8e"></a>
  <a href="CITATION.cff"><img alt="Cite this software" src="https://img.shields.io/badge/cite-CITATION.cff-0b0a06"></a>
</p>

KurrentScholar is an open-source Windows desktop application for turning scanned historical German
Kurrent handwriting into editable, auditable text. It detects individual writing lines, runs open TrOCR
models locally, presents source and transcription together for correction, and preserves model,
segmentation, and verification provenance in a reusable project.

No Python installation, API key, account, or paid AI subscription is required. Manuscript images and
transcriptions stay on your computer. Internet access is needed only when you explicitly install a model.

## Download for Windows

**[Download KurrentScholar for Windows 10/11 x64](https://github.com/98JoHu/KurrentScholar/releases/latest/download/KurrentScholar-Setup-Windows-x64.exe)**

The same [GitHub Release](https://github.com/98JoHu/KurrentScholar/releases/latest) contains
`SHA256SUMS.txt`. The current installer is not code-signed, so Windows may show an unknown-publisher
warning. Verify that the download URL starts with `https://github.com/98JoHu/KurrentScholar/` and compare
the checksum; do not disable Windows security.

Recommended minimums are Windows 10 or 11 x64, 8 GB RAM, and roughly 3 GB free disk space for the
application, one recognition model, and installation headroom. Recognition is CPU-only and adapts its
thread count to the processors available to the application. A GPU is not required.

## First use

1. Install and open KurrentScholar. The welcome tour introduces the actual controls.
2. Accept the one-time model installation prompt. Transcription cannot run without a recognition model.
3. Open a PDF, PNG, JPEG, or TIFF and choose where to save the local `.ksproj` research project.
4. Transcribe the current page, a page range such as `3-8,12`, or the full document.
5. Review results while transcription continues. Hovering or selecting a line highlights its source box;
   correct the text and mark it verified only after comparison with the manuscript.
6. Auto Save is on by default. Export the project as text, Word, CSV, Excel, or provenance-rich JSON.

The default model download is about 1.34 GB. Interrupted downloads can be continued from **Models >
Model Manager**. After installation, ordinary transcription loads the pinned files locally and works
offline.

## What is included

- Adaptive line-oriented segmentation for predominantly horizontal Kurrent pages, with spatially
  separated regions kept distinct.
- Local TrOCR inference with pinned model revisions, safetensors integrity checks, beam-search confidence
  evidence, and CPU-safe defaults.
- Live page-scoped transcription, cancellation, direct page navigation, synchronized overlays, editable
  text, correction history, and human verification.
- Default-on Auto Save and schema-versioned SQLite projects that preserve machine output separately from
  edited text.
- A model manager showing installed, partial, or damaged models and disk use, with repair and safe removal.
- UTF-8 text, Word, formula-safe CSV, standards-compliant Excel, and provenance-rich JSON exports.
- Verified ground-truth bundles and CER/WER evaluation for responsible external adaptation workflows.
- An optional Apache-2.0 local helper that answers navigation questions with curated in-app guidance and
  does not need manuscript content.
- Persistent application, crash, and responsiveness logs under
  `%LOCALAPPDATA%\KurrentScholar\Logs` for troubleshooting.

## Accuracy and research use

KurrentScholar assists transcription; it does not certify it. Difficult handwriting, faded scans,
marginalia, tables, crossed-out text, unusual columns, and historical spellings can defeat either line
detection or recognition. Confidence is a review signal, not a probability that a line is correct.
Important readings should be checked against the source and marked verified by a person.

The default checkpoint is
[`dh-unibe/trocr-kurrent`](https://huggingface.co/dh-unibe/trocr-kurrent), pinned to an exact revision.
Additional Bern Kurrent checkpoints can be installed through the same model manager for period-appropriate
comparison. A project records the model actually used and prevents silent mixing of checkpoints. Model
changes require a project backup and clean retranscription.

The included OpenCV segmenter is a practical packageable fallback, not a universal historical-layout
model. Existing projects created by an older detector can use **Transcription > Re-segment document**;
KurrentScholar creates a backup before replacing derived boxes and transcription results.

See the [user guide](docs/USER_GUIDE.md), [research methodology](docs/RESEARCH_METHODOLOGY.md),
[privacy notes](docs/PRIVACY.md), and [troubleshooting guide](docs/TROUBLESHOOTING.md).

## Running from source

Development uses Python 3.11 and [`uv`](https://docs.astral.sh/uv/):

```powershell
git clone https://github.com/98JoHu/KurrentScholar.git
cd KurrentScholar
uv python install 3.11
uv sync --extra dev --frozen
uv run kurrentscholar
```

Run the release checks with:

```powershell
uv lock --check
uv run ruff check .
uv run pytest -m "not real_model"
```

Windows packaging and clean-machine acceptance steps are documented in
[Installation and build](docs/INSTALLATION.md) and [Publishing](docs/PUBLISHING.md).

## Citation

If KurrentScholar contributes to research, cite the exact software release and separately cite the
recognition model recorded in the project or export. GitHub's **Cite this repository** control reads
[`CITATION.cff`](CITATION.cff); a ready-to-use BibTeX record is also available in
[`CITATION.bib`](CITATION.bib).

```bibtex
@software{hummel_2026_kurrentscholar,
  author       = {Hummel, Jonas},
  title        = {KurrentScholar: Offline Historical Kurrent Handwriting Transcription},
  year         = {2026},
  version      = {0.1.3},
  institution  = {Karlsruhe Institute of Technology (KIT)},
  url          = {https://github.com/98JoHu/KurrentScholar},
  license      = {MIT}
}
```

The original default recognition model has its own DOI:
[`10.57967/hf/0442`](https://doi.org/10.57967/hf/0442). KurrentScholar did not develop or train the
upstream recognition models.

## Support and contributing

For bugs and feature requests, use [GitHub Issues](https://github.com/98JoHu/KurrentScholar/issues) or
contact [Jonas Hummel](mailto:jonas.hummel@kit.edu) at Karlsruhe Institute of Technology (KIT).
Research profiles: [ORCID](https://orcid.org/0009-0005-8563-6175),
[Google Scholar](https://scholar.google.com/citations?user=l7I14bQAAAAJ&hl=de), and
[LinkedIn](https://www.linkedin.com/in/jonas-hummel/).

Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Please report security issues privately
according to [SECURITY.md](SECURITY.md), and never attach confidential manuscripts to a public issue.

## License

KurrentScholar's original source code is released under the [MIT License](LICENSE). Third-party libraries,
recognition models, and optional helper models retain their own licenses and attribution requirements; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
