# Troubleshooting

- **Model download stops:** retry; completed files should resume. Check internet access and at least 1.8 GB
  free storage. No project data is changed by model installation. The error dialog identifies common TLS,
  proxy, firewall, permission, and timeout failures. Technical details are saved in
  `%LOCALAPPDATA%\KurrentScholar\Logs\kurrentscholar.log`.
- **The interface stops responding:** wait at least 15 seconds, then close it if necessary. The GUI watchdog
  records all Python thread stacks in `kurrentscholar.log`, while fatal Python/native failures are written
  to `%LOCALAPPDATA%\KurrentScholar\Logs\kurrentscholar-crash.log`. The **Diagnostic log** toolbar action
  shows both paths. Include both files with a bug report.
- **Transcription is slow:** CPU inference of a 334M-parameter model is substantial. Process fewer pages;
  do not rely on unmeasured time estimates. The diagnostic log records the CPUs available to the process,
  PyTorch intra/inter-operation thread counts, MKLDNN availability, and decoder-cache state. Explicit
  `OMP_NUM_THREADS` or `MKL_NUM_THREADS` settings are respected; remove unintended overrides before
  comparing performance.
- **Text is missing or lines are wrong:** the fallback segmenter is weakest on columns, marginalia, curves,
  tables, damage, severe bleed-through, and crossed text. Use **Re-segment** after installing a detector
  update; the app backs up the old project before replacement. Keep problematic pages for manual review;
  no detected region is a verified blank.
- **Recognition is poor:** verify that overlays contain one complete horizontal line. The model principally
  targets nineteenth-century German Kurrent and may transfer poorly to other scripts/periods.
- **PDF will not open:** encrypted, damaged, unusually large, or parser-hostile files are rejected. Work from
  an authorized archival image copy; never overwrite the original.
- **Export fails:** choose a writable destination and close an already open DOCX/CSV. Projects remain saved.
- **Windows warns about the installer:** verify the release URL and published SHA-256. A pre-release unsigned
  build may trigger reputation warnings; do not disable SmartScreen or antivirus system-wide.

