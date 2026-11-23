# User guide

Open a manuscript with the toolbar or drag it into the window. Choose a `.ksproj` destination; the original
is never overwritten. The left panel displays the source and line boxes. The right panel lists generated
lines, explicit uncertainty labels, and editable text. Selecting a list row highlights its parent source line.
Hovering over a listed transcription temporarily highlights the same source box without changing selection.

At first startup, accept **Install model**; the application cannot transcribe until this one-time,
approximately 1.34 GB download has completed and passed its integrity checks. You can defer it and use
**Install model** later. Documents are not uploaded, and the model is used offline afterward.

Then choose **Transcribe**. Work completed before cancellation or a later error is committed incrementally.
A page can be opened directly with the toolbar selector or **View > Go to page…**; Previous/Next remain
available for sequential review. While transcription runs, live line boxes use the stored detection geometry
immediately and remain aligned with the lower-resolution viewer image.
A page with no detected lines is marked as a segmentation failure;
this is not evidence that the page is blank. Edits are stored separately from the original machine output.
Mark a line verified only after comparison with the manuscript.

**Review > Auto Save** is enabled by default and persists across launches. Turn it off if you prefer explicit
**Ctrl+S** saves; KurrentScholar still protects the active edit before switching context or closing.

Drag the divider between the line list and transcription editor to give the editor more or less height.
The text-size control is remembered across launches. Select text and use `x²` / `x₂` (or
**Ctrl+Shift+=** / **Ctrl+=**) for superscript and subscript. The special-character menu includes German
letters and common archival signs; normal Unicode keyboard input is preserved. Highlight applies a visual
mark. Tag applies a named color to a word or selection; Person, Place, Organization, Date, Unclear, and
custom labels are available. These ranges are stored in the project and included in rich/structured
exports. Plain-text export deliberately contains only the characters.

Opening a version-1 project in KurrentScholar 1.1 upgrades its schema once. Before changing the original,
the application creates a sibling file named `.schema-v1-backup.ksproj`; keep that recovery copy until the
upgraded project has been checked.

Use **Recognition model** to inspect or change the checkpoint assigned to a project. Existing projects
retain their recorded checkpoint. Changing a processed project first creates a separate backup and then
clears derived line results, because outputs from two models must not be mixed. Install the desired pinned
model with **Install model** before selecting it.

After correcting a representative sample, mark each completed line verified and choose **Evaluate
corrections**. The report gives CER, WER, exact-line rate, and results by model-score band. With no verified
lines, KurrentScholar correctly refuses to claim an accuracy figure.

Choose **Re-segment** after a line-detector update or when you deliberately want to replace all current
boxes and OCR output. KurrentScholar first creates a timestamped `.ksproj` backup beside the open project.
Corrections and review decisions remain available in that backup but are not automatically transferable
to changed line geometry.

The top-level **Export** menu provides all output formats. Exports can use corrected or
machine text and retain page/line information. CSV cells beginning with
spreadsheet formula characters are neutralized. JSON contains model/software provenance and both text
versions. Word preserves superscript, subscript, highlights, and tags; CSV, Excel, and JSON expose explicit
tag/annotation fields. DOCX uncertainty is a review aid, not calibrated accuracy.

