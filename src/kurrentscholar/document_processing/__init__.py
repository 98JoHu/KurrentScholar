"""Document rendering and page selection."""

from .pages import PageRangeError, parse_page_range
from .rendering import DocumentRenderer

__all__ = ["DocumentRenderer", "PageRangeError", "parse_page_range"]
