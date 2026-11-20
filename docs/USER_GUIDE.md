# User guide

Open a manuscript with the toolbar or drag it into the window. Choose a `.ksproj` destination; the original
is never overwritten. The left panel displays the source and line boxes. The right panel lists generated
lines, explicit uncertainty labels, and editable text. Selecting a list row highlights its parent source line.

At first startup, accept **Install model**; the application cannot transcribe until this one-time,
approximately 1.34 GB download has completed and passed its integrity checks. You can defer it and use
**Install model** later. Documents are not uploaded, and the model is used offline afterward.

Then choose **Transcribe**. Work completed before cancellation or a later error is committed incrementally.
A page with no detected lines is marked as a segmentation failure;
this is not evidence that the page is blank. Edits are stored separately from the original machine output.
Mark a line verified only after comparison with the manuscript.

Exports can use corrected or machine text and retain page/line information. CSV cells beginning with
spreadsheet formula characters are neutralized. JSON contains model/software provenance and both text
versions. DOCX uncertainty is a review aid, not calibrated accuracy.

The development UI currently lacks page thumbnails, geometry editing, metadata forms, bilingual runtime
strings, project relinking, pause/resume controls distinct from cancellation, and settings dialogs. These
are tracked honestly in `TODO.md`.

