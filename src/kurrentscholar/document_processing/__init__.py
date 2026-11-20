"""Document rendering, page selection, and processing orchestration."""

from .pages import PageRangeError, parse_page_range
from .rendering import DocumentRenderer, RenderedPage

__all__ = ["DocumentRenderer", "PageRangeError", "RenderedPage", "parse_page_range"]

