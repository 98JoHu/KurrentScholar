# Changelog

## 1.1.4 — 2026-11-26

- Added an editable reading order. Drag a line in the line list, or use **Review > Reading order > Move
  line up/down** (Alt/⌥+↑/↓), for example to read a marginal note after the main text beside it. Line boxes
  on the page are numbered in reading order (**View > Show reading order on page**), every export follows
  it, and **Restore detected order** undoes it. The detector's own numbering is kept separately, so
  resuming an interrupted transcription still matches lines correctly.
- Project schema 3 stores the reading order. Schema-2 projects are upgraded on opening after a sibling
  `.schema-v2-backup.ksproj` recovery copy is written; KurrentScholar 1.1.x cannot open upgraded projects.
- Tags are now shown at the exact words: the line list names each tag in a colored label right after its
  words, the editor underlines tagged words and names them on hover, and a row below the editor lists the
  line's tags (click to select, ✕ to remove). **Review > Tags in project…** lists, filters, and searches all
  tags and opens the tagged words. Tagging is available on right-click and with Ctrl/⌘+Shift+G; custom tag
  names are offered again, and custom tags no longer borrow a predefined tag's color. Unclear is no longer
  the same yellow as a highlight.
- Fixed formatting leaking between lines: with the caret inside a tagged, highlighted, or superscript word,
  selecting another line applied that formatting to the entire other line and saved it on leaving.
- Fixed **Clear format** leaving tags and highlights in place, and typing right after a tagged word
  extending the tag to the new text. A highlight now survives tagging and later removal of the tag.
- Exports name tags at their words: Word shows the tag's name after the tagged words in its color; CSV and
  Excel list `Tag: words` instead of only tag names; JSON adds a `tags` list with text and offsets. Line
  numbers in exports follow the reading order.

## 1.1.3 — 2026-11-26

- Fixed line detection merging two to four neighbouring lines into one box on densely written pages. Weak
  profile peaks were merged within a fixed distance of 1/30 of the page height, which exceeds the line
  spacing of typical Kurrent pages; suppression is now relative to each page's measured line spacing and
  never crosses a clear gap of paper. On a 66-page test document, boxes now match single lines (median
  height 90–170 px instead of 130–370 px at 300 DPI).
- Ink is separated from paper after correcting uneven illumination, so darker page regions in phone or
  CamScanner images no longer become ink that swallows short lines into large, mostly empty boxes.
- The line detector version is now 4. Projects processed with an older detector are offered the existing
  backup-and-re-segment step before further transcription, so old and new boxes are never mixed.
- Fixed the macOS CI failure of the tutorial layout test, which depended on platform font metrics.
  This failure prevented macOS DMGs for 1.1.2; 1.1.3 is the first release containing the 1.1.2 changes
  for both Windows and macOS.

## 1.1.2 — 2026-11-26

- Fixed invisible text on macOS in Dark Mode: the line list, editor, menus, and inputs rendered light text
  on the light interface. The application now requests the light color scheme and sets explicit text colors.
- Live transcription no longer moves the reviewer's text cursor or line-list scroll position each time a
  new line is saved on the page being corrected.
- Spin-box arrows (page selector, text size) are drawn with bundled images, so they no longer appear
  broken on macOS.
- Keyboard shortcuts now work the same way on Windows and macOS and on German keyboards: superscript and
  subscript use Ctrl/⌘+. and Ctrl/⌘+, , clear formatting uses Ctrl/⌘+Shift+Space (Cmd+Space opens
  Spotlight), next uncertain line adds Ctrl/⌘+Shift+N, and Fit page gains Ctrl/⌘+0. Previous shortcuts
  remain as alternates. Tooltips and messages show the platform's own key names.
- Removed unused code: the image preprocessing module, an unused segmentation protocol, page rotation
  support, constant aliases, never-used model, status, and export options, and the never-populated project
  metadata (the always-empty `metadata` key is no longer written to research JSON).
- Marking a line verified now saves its pending edit first. Messages that referred to the removed
  "Install model" button now point to **Models > Model Manager**; documentation lists macOS log locations.
- Fixed a model download being reported as failed (and its progress showing another model) when a
  transcription or model selection happened during the download. Installing or removing another model
  while a download runs is now refused with an explanation.
- Multi-page TIFF files now open with all pages; previously only the first page was available.
- The review list marks verified lines with ✓, explains failed or truncated recognitions in a tooltip, and
  **Next uncertain line** skips lines that are already verified.
- Ground-truth bundles now crop lines from the deskewed page exactly as recognition did, so training images
  match model input on slanted pages; the manifest records each line's deskew angle.
- Export dialogs suggest a file beside the project instead of the program's working folder (which was the
  read-only system root on macOS). A page that cannot be displayed, for example on a disconnected drive,
  now shows a message instead of leaving the window half-updated.
- macOS DMGs include the license and third-party notices, and App Nap no longer slows transcription while
  the window is in the background.

## 1.1.1 — 2026-11-24

- First release with signed and notarized macOS DMGs for Apple Silicon and Intel, built natively on
  both architectures; Windows and macOS releases can now be published concurrently.
- CI tests every distributed platform (Windows, Apple Silicon macOS, Intel macOS).
- Note: the 1.1.1 application still reported its version as 1.1.0.

## 1.1.0 — 2026-11-23

- Removed KurrentBot, its optional language model, configuration, packaging hooks, documentation, and UI
  entry points after field use showed that curated in-app help did not justify its complexity or disk use.
- Removed duplicate Export and Save toolbar controls. Export remains a clear top-level menu, Save retains
  its standard shortcut, and Auto Save remains enabled by default.
- Added conservative ±7° page deskewing before line detection and recognition. OCR receives horizontal
  crops while source overlays retain rotated polygon geometry on the unmodified manuscript image.
- Added a vertically resizable transcription editor, persistent user-selected text size, UTF-8 special
  character insertion, Word-like superscript/subscript shortcuts, highlights, and named or custom word tags.
- Migrated projects transactionally from schema 1 to schema 2. Rich annotations and polygon geometry now
  survive reopening and are represented in Word, CSV, Excel, and research JSON exports.
- Added native Apple Silicon and Intel macOS packaging with mandatory Developer ID signing, notarization,
  stapling, architecture-specific checksums, and stable GitHub Release download names.
- Documented Zenodo release archiving for a genuine version DOI and concept DOI without inventing a
  placeholder identifier.

## 1.0.0 — 2026-11-21

- Fixed Excel repair warnings by removing the duplicate worksheet/table AutoFilter declaration and
  omitting empty inline-string cells; validated the repaired output in desktop Microsoft Excel.
- Added the KurrentScholar Kurrent-letter logo to the application, Windows executable, installer, and
  repository documentation.
- Added complete maintainer/citation metadata and tagged-release automation that publishes the tested
  installer and SHA-256 checksum as directly downloadable GitHub Release assets.

- Reworked onboarding into a control-anchored spotlight tour beginning with a clear welcome and purpose;
  redesigned the local helper as an upper-right KurrentBot launcher with a persistent right-side chat panel.
- Added a top-level Export menu and toolbar entry, direct page-number navigation, and a persistent Auto Save
  toggle that defaults on.
- Fixed transient live-transcription box misalignment by applying the 300-DPI detection-to-150-DPI viewer
  transform as soon as page geometry is stored; hovering a transcription now highlights its source box.

- Added current-page, page-range, and full-document transcription. The project remains open through
  SQLite WAL while processing, so committed lines appear live and completed pages remain navigable/editable.
- Replaced the crowded flat toolbar with grouped File, Transcription, Review, Models, View, and Help menus
  plus a slim primary toolbar; added first-start onboarding and a replayable tutorial.
- Added native Excel workbooks with transcription, summary, and provenance sheets; Word and CSV now have
  explicit export entries alongside text and research JSON.
- Added verified ground-truth ZIP bundles with line crops, UTF-8 labels, source checksum, base-model
  provenance, reference pages, and intended target pages for responsible external GPU fine-tuning.
- Added a model manager with installation/repair state, disk usage, safe removal (including partial
  downloads), and project model selection. Added Bern's MIT 16th–18th-century TrOCR checkpoint.
- Added an optional Apache-2.0 SmolLM2 135M local help model. A real-weight audit showed that unrestricted
  generation fabricated UI instructions, so the released design constrains it to intent classification
  and returns curated, tested navigation guidance instead.
- Added OpenEarable-inspired warm rose accents, pale backgrounds, flat rounded surfaces, and quieter
  uncertainty colors without copying its assets or functionality.
- Prevented accidental project replacement without a second explicit confirmation and added moved-source
  relinking guarded by the original SHA-256 checksum.

- Added a pinned model catalog with Bern's broad 16th–19th-century Kurrent checkpoint as an experimental
  comparison while preserving the original 19th-century checkpoint as the established default.
- Added safe per-project model selection. A project cannot silently mix checkpoints; changing models
  requires a complete backup before resetting derived transcription results.
- Added verified-line project evaluation with CER, WER, exact-line rate, and confidence-band diagnostics.
  Unverified edits are excluded so incomplete corrections cannot become accidental ground truth.
- Fixed export provenance to cite the model actually recorded in the project.
- Enabled autoregressive decoder key/value caching during TrOCR inference. This retains the pinned FP32
  model, processor, four-beam decoding, token limit, and confidence scoring while avoiding repeated decoder
  work; a real-crop benchmark produced identical text with roughly 2.4× higher throughput.
- Added affinity-aware CPU runtime configuration and diagnostics. PyTorch's hardware-tuned thread defaults
  are retained unless they exceed the processors available to the process, while explicit OpenMP/MKL
  administrator settings remain authoritative.
- Benchmarked and rejected line batching as a default: batch 2 was effectively neutral and larger batches
  were substantially slower for variable-length autoregressive lines on the tested CPU.

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

