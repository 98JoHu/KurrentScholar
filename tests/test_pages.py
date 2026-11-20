import pytest

from kurrentscholar.document_processing.pages import PageRangeError, parse_page_range


def test_page_range_is_ordered_and_unique():
    assert parse_page_range("3,1-2,2", 4) == [2, 0, 1]


@pytest.mark.parametrize("value", ["0", "4", "3-1", "one"])
def test_page_range_rejects_invalid(value):
    with pytest.raises(PageRangeError):
        parse_page_range(value, 3)

