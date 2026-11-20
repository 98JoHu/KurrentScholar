from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate transparent CER/WER metrics")
    parser.add_argument("reference", type=Path)
    parser.add_argument("hypothesis", type=Path)
    arguments = parser.parse_args()
    result = evaluate(arguments.reference.read_text("utf-8"), arguments.hypothesis.read_text("utf-8"))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

