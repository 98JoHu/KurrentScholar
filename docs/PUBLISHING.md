# Publishing and archiving

1. Create a public GitHub repository under the maintainer's chosen account and replace every
   `TO-BE-PROVIDED` value. Do not publish until archival fixtures and licenses are reviewed.
2. Push source only; confirm `.gitignore` excludes weights, projects, caches, documents, and binaries.
3. Protect the default branch and require CI. Create a signed source tag only after updating version,
   changelog, citation, and lock file.
4. Run the Windows artifact workflow, verify its SHA-256, then perform install/start/model-download/
   import/transcribe/save/reopen/export/uninstall acceptance on a clean Windows x64 VM without Python.
5. Create a GitHub release and attach only the tested installer and checksum. State that it is unsigned
   unless it has actually been signed. Never fabricate download links.
6. Enable the repository in Zenodo, create the GitHub release, let Zenodo archive it, then reserve/publish
   the record after reviewing metadata. Put the real version DOI in `CITATION.cff`; use the concept DOI
   for all-version references and the version DOI for reproducible citations.

Before publication the maintainer must supply their name, ORCID (optional), institution, repository URL,
support/security contacts, release license decision, software DOI, and any code-signing identity.

