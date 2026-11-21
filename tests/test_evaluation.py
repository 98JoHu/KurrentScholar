from types import SimpleNamespace

from kurrentscholar.evaluation import error_rate, evaluate_project_lines


def test_error_rate_breakdown():
    result = error_rate(list("abc"), list("adc!"))
    assert result.distance == 2
    assert result.substitutions == 1
    assert result.insertions == 1
    assert result.deletions == 0
    assert result.rate == 2 / 3


def test_project_evaluation_uses_only_verified_human_reference():
    lines = [
        SimpleNamespace(
            machine_text="abc",
            corrected_text="adc",
            review_status="verified",
            confidence=0.8,
        ),
        SimpleNamespace(
            machine_text="ignored",
            corrected_text="different",
            review_status="unreviewed",
            confidence=0.99,
        ),
        SimpleNamespace(
            machine_text="exact",
            corrected_text=None,
            review_status="verified",
            confidence=0.95,
        ),
    ]

    report = evaluate_project_lines(lines)

    assert report["verified_reference_lines"] == 2
    assert report["excluded_unverified_lines"] == 1
    assert report["cer"]["distance"] == 1
    assert report["exact_line_rate"] == 0.5
    assert report["confidence_bands"]["moderate"]["error_lines"] == 1


def test_project_evaluation_does_not_claim_accuracy_without_ground_truth():
    line = SimpleNamespace(
        machine_text="text",
        corrected_text=None,
        review_status="unreviewed",
        confidence=0.99,
    )
    report = evaluate_project_lines([line])
    assert report["verified_reference_lines"] == 0
    assert report["exact_line_rate"] is None
    assert "No accuracy" in report["calibration_warning"]

