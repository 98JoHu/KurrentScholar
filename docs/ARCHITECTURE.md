# Architecture

KurrentScholar is an offline-first, layered desktop application. Qt depends on application services;
application services depend on domain interfaces; adapters implement PDF, segmentation, recognition,
SQLite, and export concerns. No recognition or PDF operation runs on the GUI thread.

```text
Qt UI -> processing service -> renderer -> segmenter -> recognizer
                    |                              |
                    +----------> SQLite <----------+
                                      |
                                  exporters
```

## Core boundaries

- `domain.py`: stable value objects (`BoundingBox`, `RecognitionResult`, confidence and review states).
- `document_processing`: bounded PDF/image decoding and page selection.
- `segmentation`: the OpenCV projection detector, which detects
  independent ink-density peaks, separates them at projection valleys, and derives connected extents
  within each line region. It is deterministic and packageable on Windows, but not equivalent to a
  learned historical-layout model.
- `recognition`: pinned model manifest/installer and TrOCR adapter. The adapter
  accepts only a line image, loads with `local_files_only=True` and `use_safetensors=True`, and uses
  autoregressive decoder caching without changing model weights or decoding strategy.
- `projects`: schema-versioned SQLite. `machine_text` and model scores are never overwritten when
  `corrected_text` changes. Writes use transactions, WAL, foreign keys, and incremental commits.
- `exports`: representations are derived from stored provenance and escape spreadsheet formula cells.
- `ui`: presentation and worker coordination; it contains no model logic.

## Architectural decisions

### ADR-001: SQLite project files

SQLite provides atomic local writes, recovery after interruption, migrations, and portable inspection.
Original documents remain external by default and are identified by path and SHA-256. A future package
operation may copy them only after explicit authorization.

### ADR-002: model files remain separate

The Windows installer is kept manageable and redistribution simple. An explicit wizard downloads one
pinned revision and a manifest excludes `.bin`, optimizer, and trainer files. Ordinary inference is
strictly local afterward.

### ADR-003: fallback segmentation is replaceable

Kraken is powerful, but its Windows/native dependency surface and separate model selection need clean
build validation. The first shippable backend uses OpenCV projection peaks and valleys. Every line
retains a bounding box and can be reprocessed individually. Detector versions are stored in the project;
incompatible results require an explicit backed-up reset instead of ordinal reuse. A learned backend can
implement the protocol without changing recognition.

### ADR-004: confidence is evidence, not accuracy

Generation transition probabilities are stored as raw token evidence. Threshold labels are provisional.
Human edits never receive invented model scores. Word highlighting is withheld unless tokenizer offsets
provide defensible alignment; current UI highlights lines.

## Threat model

Inputs are untrusted. Render one page at a time, bound DPI/page ranges/image dimensions, use parameterized
SQL, reject unsafe export destinations, avoid document text in logs, and never load remote Python code.
Model download is the only built-in network path and is initiated by the user.

## Schema evolution

`PRAGMA user_version` records the schema version. Migrations are forward-only and transactional. A newer
project version is rejected with a useful error instead of being silently modified.

