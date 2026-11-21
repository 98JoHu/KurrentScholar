# Publishing and archiving

1. Confirm the version matches in `pyproject.toml`, `src/kurrentscholar/__init__.py`,
   `packaging/windows/KurrentScholar.iss`, `CITATION.cff`, and the changelog.
2. Run `uv lock --check`, `uv run ruff check .`, and `uv run pytest -m "not real_model"`.
3. Build locally and run `dist/KurrentScholar/KurrentScholar.exe --smoke-test`. Compile the installer and
   verify its SHA-256.
4. Install/start/import/transcribe/save/reopen/export/uninstall on a clean Windows 10 or 11 x64 VM without
   Python. Confirm a real model installation and open DOCX/XLSX exports in Microsoft Office.
5. Commit and push, then create an annotated tag such as `v1.0.0` at that exact commit. Pushing the tag
   runs the Windows release workflow; after tests and the packaged smoke test pass, it creates the GitHub
   Release and attaches the stable-name installer plus `SHA256SUMS.txt`.
6. Download the published asset through the README's direct link and compare its hash. The installer is
   unsigned unless a protected code-signing step has actually been configured.
7. Optionally enable the repository in Zenodo before the next release. Add a DOI to `CITATION.cff` only
   after the archival record exists; never publish a placeholder DOI.

