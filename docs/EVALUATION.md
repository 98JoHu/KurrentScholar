# Evaluation methodology

No benchmark has been executed for KurrentScholar yet, and no result is claimed. The upstream model card
reports line-level results on its own nineteenth-century collections; they do not measure this application's
page segmentation, different archives, Sütterlin, earlier hands, damage, or editorial review workflow.

`kurrentscholar-evaluate reference.txt hypothesis.txt` computes Levenshtein distance twice:

- CER uses Python Unicode code points, including whitespace and punctuation, with no normalization.
- WER uses `str.split()` whitespace-delimited tokens, preserving case and punctuation attached to words.
- For both, `rate = (substitutions + insertions + deletions) / reference units`.
- Empty-reference rate is 0 for an empty hypothesis and 1 for a nonempty hypothesis.

`kurrentscholar-evaluate --project research.ksproj` evaluates only lines explicitly marked verified.
For corrected verified lines, the correction is the reference and immutable machine output is the
hypothesis. A verified line that needed no edit is an exact reference. Unverified edits are excluded so
an interrupted correction cannot silently enter the ground truth. The report includes aggregate CER/WER,
exact-line rate, and the same metrics grouped by the provisional model-score labels.

The utility reports substitutions, insertions, deletions, distance, denominator, and rate. Evaluation must
separate (a) provided ground-truth line crops, measuring recognizer behavior, from (b) complete pages,
measuring segmentation plus recognition. Line matching and missed/extra-region rules must be published
with each dataset.

Before confidence calibration, acquire reusable ground truth with provenance, divide writers/documents
into disjoint calibration and test sets, and plot error prevalence against stored line score. Select
thresholds only on calibration data; publish reliability diagrams, coverage, sample sizes, confidence
intervals, and final untouched test results. Record hardware, software/model revisions, generation
parameters, processing time, and segmentation backend. Never infer calibration from the upstream CER.

