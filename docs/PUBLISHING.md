# Publishing and archiving

## Release checklist

1. Confirm the version matches in `pyproject.toml`, `src/kurrentscholar/__init__.py`,
   `packaging/windows/KurrentScholar.iss`, `CITATION.cff`, `CITATION.bib`, and the changelog. Replace
   “unreleased” with the release date.
2. Run `uv lock --check`, `uv run ruff check .`, and `uv run pytest -m "not real_model"`.
3. Build locally and run `dist/KurrentScholar/KurrentScholar.exe --smoke-test`. Compile the installer and
   verify its SHA-256.
4. Install/start/import/transcribe/save/reopen/export/uninstall on a clean Windows 10 or 11 x64 VM without
   Python. Confirm a real model installation and open DOCX/XLSX exports in Microsoft Office.
5. Confirm all six protected Apple secrets listed in `packaging/macos/README.md` are configured. macOS jobs
   intentionally fail rather than publish unsigned or unnotarized DMGs.
6. Commit and push, then create an annotated tag such as `v1.1.0` at that exact commit. Pushing the tag runs
   the Windows and macOS release workflows. Windows creates the GitHub Release; the two native Mac jobs
   attach their signed/notarized architecture-specific DMGs after the release exists.
7. On clean Apple Silicon and Intel Macs, verify Gatekeeper acceptance, first launch, model installation,
   document import, transcription, reopen, all exports, and removal. A green CI job is not a replacement
   for these acceptance checks.
8. Download every published asset through the README links, compare each published checksum, and inspect
   the generated release notes. The Windows installer remains unsigned until Windows signing is explicitly
   added; the Mac assets must never be published without Apple notarization.

## Obtain a DOI for KurrentScholar

Zenodo's GitHub integration creates a genuine DOI for an archived GitHub release; it is preferable to a
home-grown “DOI-like” string. It also assigns a concept DOI representing the software across versions and
a distinct version DOI for each archived release.

1. Sign in to Zenodo with the GitHub account that controls `98JoHu/KurrentScholar`.
2. In Zenodo's GitHub settings, enable the KurrentScholar repository **before** publishing the next GitHub
   release. Repository access may need to be refreshed if it is not listed.
3. Publish the tested GitHub release. Zenodo should ingest the tagged source archive and the metadata from
   `CITATION.cff`. Check author, ORCID, KIT affiliation, title, software type, license, version, date, and
   repository URL before publishing the Zenodo record.
4. Copy the resulting **version DOI** into that release's `CITATION.cff`/`CITATION.bib` and release notes.
   Use the **concept DOI** for badges or general project references that should always resolve to the newest
   archived version. Never insert a guessed or reserved placeholder DOI into a published citation file.
5. If the already-published release was not captured automatically, upload its GitHub source archive to a
   Zenodo software record manually, using the same version and metadata. Do not create two records for the
   same release.

Software Heritage can additionally archive the repository and issue an SWHID. An SWHID is a useful,
content-addressed preservation identifier, but it is not a DOI and should complement—not impersonate—the
Zenodo citation.

