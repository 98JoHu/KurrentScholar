from kurrentscholar.evaluation import error_rate


def test_error_rate_breakdown():
    result = error_rate(list("abc"), list("adc!"))
    assert result.distance == 2
    assert result.substitutions == 1
    assert result.insertions == 1
    assert result.deletions == 0
    assert result.rate == 2 / 3

