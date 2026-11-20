# Troubleshooting

- **Model download stops:** retry; completed files should resume. Check internet access and at least 1.8 GB
  free storage. No project data is changed by model installation.
- **Transcription is slow:** CPU inference of a 334M-parameter model is substantial. Process fewer pages;
  do not rely on unmeasured time estimates.
- **Text is missing or lines are wrong:** the fallback segmenter is weakest on columns, marginalia, curves,
  tables, damage, bleed-through, and crossed text. Keep the page for manual review; no detected region is
  a verified blank.
- **Recognition is poor:** verify that overlays contain one complete horizontal line. The model principally
  targets nineteenth-century German Kurrent and may transfer poorly to other scripts/periods.
- **PDF will not open:** encrypted, damaged, unusually large, or parser-hostile files are rejected. Work from
  an authorized archival image copy; never overwrite the original.
- **Export fails:** choose a writable destination and close an already open DOCX/CSV. Projects remain saved.
- **Windows warns about the installer:** verify the release URL and published SHA-256. A pre-release unsigned
  build may trigger reputation warnings; do not disable SmartScreen or antivirus system-wide.

