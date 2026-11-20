from __future__ import annotations


class PageRangeError(ValueError):
    pass


def parse_page_range(specification: str, page_count: int) -> list[int]:
    """Parse a one-based user page range into unique zero-based page indices."""
    if page_count < 1:
        raise PageRangeError("The document has no pages")
    text = specification.strip().lower()
    if text in {"", "all", "alle"}:
        return list(range(page_count))
    pages: list[int] = []
    seen: set[int] = set()
    try:
        for chunk in text.split(","):
            bounds = [int(part.strip()) for part in chunk.split("-")]
            if len(bounds) == 1:
                sequence = bounds
            elif len(bounds) == 2 and bounds[0] <= bounds[1]:
                sequence = range(bounds[0], bounds[1] + 1)
            else:
                raise PageRangeError("Use ranges such as 1-3,5")
            for one_based in sequence:
                if one_based < 1 or one_based > page_count:
                    raise PageRangeError(f"Page {one_based} is outside 1-{page_count}")
                index = one_based - 1
                if index not in seen:
                    pages.append(index)
                    seen.add(index)
    except ValueError as error:
        raise PageRangeError("Use page numbers and ranges such as 1-3,5") from error
    return pages

