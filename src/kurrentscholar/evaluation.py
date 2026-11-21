from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kurrentscholar.domain import ConfidenceThresholds


@dataclass(frozen=True, slots=True)
class ErrorRate:
    distance: int
    reference_units: int
    rate: float
    substitutions: int
    insertions: int
    deletions: int


def error_rate(reference: list[str], hypothesis: list[str]) -> ErrorRate:
    rows, columns = len(reference) + 1, len(hypothesis) + 1
    table = [[(0, 0, 0, 0)] * columns for _ in range(rows)]
    for i in range(1, rows):
        table[i][0] = (i, 0, 0, i)
    for j in range(1, columns):
        table[0][j] = (j, 0, j, 0)
    for i in range(1, rows):
        for j in range(1, columns):
            if reference[i - 1] == hypothesis[j - 1]:
                table[i][j] = table[i - 1][j - 1]
                continue
            candidates = [
                tuple(sum(pair) for pair in zip(table[i - 1][j - 1], (1, 1, 0, 0), strict=True)),
                tuple(sum(pair) for pair in zip(table[i][j - 1], (1, 0, 1, 0), strict=True)),
                tuple(sum(pair) for pair in zip(table[i - 1][j], (1, 0, 0, 1), strict=True)),
            ]
            table[i][j] = min(candidates, key=lambda item: item[0])
    distance, substitutions, insertions, deletions = table[-1][-1]
    return ErrorRate(distance, len(reference), distance / len(reference) if reference else float(bool(hypothesis)),
                     substitutions, insertions, deletions)


def evaluate(reference: str, hypothesis: str) -> dict[str, object]:
    return {
        "cer": asdict(error_rate(list(reference), list(hypothesis))),
        "wer": asdict(error_rate(reference.split(), hypothesis.split())),
    }


def _combined_error_rate(rates: Iterable[ErrorRate]) -> ErrorRate:
    collected = list(rates)
    distance = sum(rate.distance for rate in collected)
    reference_units = sum(rate.reference_units for rate in collected)
    return ErrorRate(
        distance=distance,
        reference_units=reference_units,
        rate=distance / reference_units if reference_units else 0.0,
        substitutions=sum(rate.substitutions for rate in collected),
        insertions=sum(rate.insertions for rate in collected),
        deletions=sum(rate.deletions for rate in collected),
    )


def evaluate_project_lines(lines: Iterable[Any]) -> dict[str, object]:
    """Evaluate only human-verified lines, preserving raw transcription conventions.

    A verified corrected line uses the correction as reference. A verified unedited
    line uses the machine text as its human-confirmed reference. Merely autosaving a
    correction is not enough: incomplete edits must not silently become ground truth.
    """

    all_lines = list(lines)
    verified = [line for line in all_lines if line.review_status == "verified"]
    thresholds = ConfidenceThresholds()
    records = []
    for line in verified:
        reference = line.corrected_text if line.corrected_text is not None else line.machine_text
        hypothesis = line.machine_text
        cer = error_rate(list(reference), list(hypothesis))
        wer = error_rate(reference.split(), hypothesis.split())
        records.append((line, cer, wer))

    cer_total = _combined_error_rate(record[1] for record in records)
    wer_total = _combined_error_rate(record[2] for record in records)
    bands: dict[str, dict[str, object]] = {}
    for line, cer, wer in records:
        label = thresholds.classify(line.confidence).value
        band = bands.setdefault(
            label,
            {
                "lines": 0,
                "error_lines": 0,
                "confidence_sum": 0.0,
                "confidence_count": 0,
                "cer_rates": [],
                "wer_rates": [],
            },
        )
        band["lines"] += 1
        band["error_lines"] += int(cer.distance > 0)
        if line.confidence is not None:
            band["confidence_sum"] += float(line.confidence)
            band["confidence_count"] += 1
        band["cer_rates"].append(cer)
        band["wer_rates"].append(wer)

    summarized_bands = {}
    for label, band in bands.items():
        confidence_count = int(band["confidence_count"])
        summarized_bands[label] = {
            "lines": int(band["lines"]),
            "error_lines": int(band["error_lines"]),
            "line_error_rate": int(band["error_lines"]) / int(band["lines"]),
            "mean_model_score": (
                float(band["confidence_sum"]) / confidence_count
                if confidence_count
                else None
            ),
            "cer": asdict(_combined_error_rate(band["cer_rates"])),
            "wer": asdict(_combined_error_rate(band["wer_rates"])),
        }

    exact = sum(record[1].distance == 0 for record in records)
    return {
        "method": "human-verified lines; exact Unicode CER; whitespace-token WER; no normalization",
        "total_lines": len(all_lines),
        "verified_reference_lines": len(records),
        "excluded_unverified_lines": len(all_lines) - len(records),
        "exact_line_rate": exact / len(records) if records else None,
        "cer": asdict(cer_total),
        "wer": asdict(wer_total),
        "confidence_bands": summarized_bands,
        "calibration_warning": (
            "No accuracy or confidence calibration conclusion is possible without verified lines."
            if not records
            else "Confidence-band results describe this verified sample only; they do not recalibrate the model."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate transparent CER/WER metrics")
    parser.add_argument("reference", type=Path, nargs="?")
    parser.add_argument("hypothesis", type=Path, nargs="?")
    parser.add_argument(
        "--project",
        type=Path,
        help="Evaluate human-verified lines in a KurrentScholar project",
    )
    arguments = parser.parse_args()
    if arguments.project:
        if arguments.reference or arguments.hypothesis:
            parser.error("--project cannot be combined with reference/hypothesis files")
        from kurrentscholar.projects import ProjectDatabase

        with ProjectDatabase(arguments.project) as project:
            result = evaluate_project_lines(project.lines())
            result["project_info"] = project.info()
    else:
        if not arguments.reference or not arguments.hypothesis:
            parser.error("provide reference and hypothesis files, or use --project")
        result = evaluate(
            arguments.reference.read_text("utf-8"),
            arguments.hypothesis.read_text("utf-8"),
        )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

