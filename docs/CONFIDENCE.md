# Confidence and uncertainty methodology

KurrentScholar requests `return_dict_in_generate=True` and `output_scores=True`, then calls
`VisionEncoderDecoderModel.compute_transition_scores(..., normalize_logits=True)`. Exponentiating each
selected transition log-score yields its conditional token probability. Decoder start, EOS, padding,
and tokenizer special tokens are excluded from aggregation.

The displayed line score is the geometric mean of the remaining token probabilities. Geometric rather
than arithmetic averaging prevents one very weak transition from disappearing and reduces direct length
bias compared with multiplying probabilities. Raw token probabilities and IDs are retained separately
from text. Human corrections do not alter them and receive no artificial confidence.

Default labels are provisional heuristics:

| Line score | Label | Non-colour cue |
|---|---|---|
| ≥ 0.90 | Higher model confidence | “higher” |
| ≥ 0.75 and < 0.90 | Moderate uncertainty | “moderate” |
| ≥ 0.50 and < 0.75 | High uncertainty | “high uncertainty” |
| < 0.50 | Very high uncertainty | “very high uncertainty” |
| unavailable | unavailable | explicit unavailable label |

These scores are not calibrated probabilities that the transcription is correct. Beam search conditions
on earlier generated tokens and its scores measure the model distribution, not historical truth. A
high-confidence error, omitted line, or segmentation failure is possible.

The current UI highlights parent lines only. Although RoBERTa BPE tokens can be decoded, reliable mapping
from generation tokens through byte-level spacing to edited word/character spans is not yet established.
KurrentScholar therefore refuses to fabricate word-level spatial or textual precision. Lines that exhaust
the configured generation limit without EOS are flagged as potentially truncated.

The **Evaluate corrections** action measures CER/WER only after a human marks lines verified. Its
confidence-band table can reveal whether the score ranks errors usefully for a particular collection, but
it does not automatically change thresholds. A representative, writer-separated calibration set is still
required before changing the defaults.

