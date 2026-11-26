# User guide

Open a manuscript with the toolbar or drag it into the window. Choose a `.ksproj` destination; the original
is never overwritten. The left panel displays the source and line boxes. The right panel lists generated
lines, explicit uncertainty labels, and editable text. Selecting a list row highlights its parent source line.
Hovering over a listed transcription temporarily highlights the same source box without changing selection.

At first startup, accept **Install model**; the application cannot transcribe until this one-time,
approximately 1.34 GB download has completed and passed its integrity checks. You can defer it and install it
later from **Models > Model Manager**. Documents are not uploaded, and the model is used offline afterward.

Then choose **Transcribe**. Work completed before cancellation or a later error is committed incrementally.
A page can be opened directly with the toolbar selector or **View > Go to page…**; Previous/Next remain
available for sequential review. While transcription runs, live line boxes use the stored detection geometry
immediately and remain aligned with the lower-resolution viewer image.
A page with no detected lines is marked as a segmentation failure;
this is not evidence that the page is blank. Edits are stored separately from the original machine output.
Mark a line verified only after comparison with the manuscript.

**Review > Auto Save** is enabled by default and persists across launches. Turn it off if you prefer explicit
**Ctrl+S** (macOS: **⌘S**) saves; KurrentScholar still protects the active edit before switching context or closing.

Drag the divider between the line list and transcription editor to give the editor more or less height.
The text-size control is remembered across launches. Select text and use `x²` / `x₂` (or
**Ctrl+.** / **Ctrl+,**) for superscript and subscript. The special-character menu includes German
letters and common archival signs; normal Unicode keyboard input is preserved. Highlight applies a visual
mark. **Clear format** removes highlights, tags, superscript, and subscript from the selection.

### Tags

Tags record what a word is: Person, Place, Organization, Date, Unclear, or a name you type yourself. Select
the words (or place the cursor inside a single word) and press **Tag…** (**Ctrl+Shift+G**), or right-click
the word and choose **Tag as**. Names you have used before in the project are offered again, so a custom tag
such as "Pfarrer" keeps one spelling and one color.

A tag's name is shown as a small colored label directly after the tagged words in the line list. In the
editor, tagged words are colored and underlined; hovering shows the tag, and the row below the editor
lists the line's tags. Click a listed tag to select its words, or **✕** to remove it; right-clicking a
tagged word also offers **Remove tag**. Typing directly after a tagged word does not extend the tag, while
corrections inside the tagged words remain part of it.

**Review > Tags in project…** lists every tag with its words, page, and line. Filter by tag or search the
tagged text, and double-click a row to open the line with the tagged words selected. Word exports show each
tag's name after its words in the tag's color; CSV and Excel name the tagged words (for example
`Person: Matthias Müller; Place: Wien`); JSON lists each tag with its text and character offsets. Plain-text
export deliberately contains only the characters.

### Reading order

Lines are first listed in the order in which they were detected, top to bottom. When a page should be read
differently, for example a marginal note after the main text beside it, drag a line to its place in the
line list, or select it and use **Review > Reading order > Move line up / Move line down**
(**Alt+↑ / Alt+↓**; macOS: **⌥↑ / ⌥↓**). The same commands are on the line list's right-click menu. The
numbers in the list, the numbered labels on the page boxes, and every export follow the new order.
**Restore detected order** returns the page to the detected order, and **View > Show reading order on page**
hides or shows the numbered labels. Changing the order never changes text, tags, or review status.

### Project upgrades

Opening a project made by an earlier version upgrades its schema once (KurrentScholar 1.1 introduced
schema 2, and the editable reading order introduced schema 3). Before changing the original, the
application creates a sibling recovery copy named `.schema-v1-backup.ksproj` or `.schema-v2-backup.ksproj`
that the earlier version can still open; keep it until the upgraded project has been checked. Older
versions cannot open an upgraded project.

Use **Recognition model** to inspect or change the checkpoint assigned to a project. Existing projects
retain their recorded checkpoint. Changing a processed project first creates a separate backup and then
clears derived line results, because outputs from two models must not be mixed. Install the desired pinned
model in **Models > Model Manager** before selecting it.

After correcting a representative sample, mark each completed line verified and choose **Evaluate
corrections**. The report gives CER, WER, exact-line rate, and results by model-score band. With no verified
lines, KurrentScholar correctly refuses to claim an accuracy figure.

Choose **Re-segment** after a line-detector update or when you deliberately want to replace all current
boxes and OCR output. KurrentScholar first creates a timestamped `.ksproj` backup beside the open project.
Corrections and review decisions remain available in that backup but are not automatically transferable
to changed line geometry.

The top-level **Export** menu provides all output formats. Exports can use corrected or
machine text and retain page/line information; line numbers follow the page's reading order. CSV cells beginning with
spreadsheet formula characters are neutralized. JSON contains model/software provenance and both text
versions. Word preserves superscript, subscript, highlights, and tags; CSV, Excel, and JSON expose explicit
tag/annotation fields (see Tags above). DOCX uncertainty is a review aid, not calibrated accuracy.

## Keyboard shortcuts

The same shortcuts work on Windows and macOS; on a Mac, press **⌘ Command** wherever this table says
**Ctrl**. Menus always show the shortcut in the platform's own notation.

| Action | Shortcut |
|---|---|
| Open document / project | Ctrl+O / Ctrl+Shift+O |
| Previous / next page | Page Up / Page Down (Mac laptops: Fn+↑ / Fn+↓) |
| Go to page | Ctrl+G |
| Transcribe current page / page range | Ctrl+T / Ctrl+Shift+T |
| Save | Ctrl+S |
| Mark selected line verified | Ctrl+Shift+V |
| Next uncertain line | Ctrl+Shift+N (also F6) |
| Move selected line up / down in reading order | Alt+↑ / Alt+↓ (macOS: ⌥↑ / ⌥↓) |
| Tag selected text | Ctrl+Shift+G |
| Superscript / subscript | Ctrl+. / Ctrl+, (also Ctrl+Shift+= / Ctrl+=) |
| Clear text formatting | Ctrl+Shift+Space (Windows also Ctrl+Space) |
| Zoom in / out / fit page | Ctrl++ / Ctrl+- / Ctrl+0 |

The period, comma, and letter keys sit in the same place on German and English keyboards, so these
shortcuts need no extra Shift or AltGr on either layout.
