"""Character-range annotations on line text: superscript, subscript, highlights, and tags.

Annotations are stored per line as ``{"start", "end", "kind", ...}`` with offsets into the
line's effective text. The editor, the line list, and the exports all read them through
these helpers so that a tag looks and reads the same everywhere.
"""

from __future__ import annotations

import colorsys
import html
import re
from dataclasses import dataclass
from typing import Any

HIGHLIGHT_COLOR = "#FFF0A8"
TAG_COLORS = {
    "Person": "#F2C7C3",
    "Place": "#C9DDF7",
    "Organization": "#DDD0F2",
    "Date": "#CDE8D2",
    # Kept apart from the yellow highlight and the uncertainty colors of the line list.
    "Unclear": "#DCE1E8",
}
# Custom labels get a stable color of their own instead of borrowing a predefined tag's.
CUSTOM_TAG_COLORS = ("#F6D3B3", "#C8E6E0", "#ECD5EE", "#DCE6C0", "#F5CFE0", "#D3DAF0", "#EADFC8")


@dataclass(frozen=True, slots=True)
class TagSpan:
    label: str
    start: int
    end: int
    text: str
    color: str


def normalized(text: str, annotations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return annotations clamped to the text, dropping malformed or empty ranges."""

    valid: list[dict[str, Any]] = []
    for annotation in annotations:
        try:
            start = max(0, min(len(text), int(annotation["start"])))
            end = max(start, min(len(text), int(annotation["end"])))
            str(annotation["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if start < end:
            valid.append({**annotation, "start": start, "end": end})
    return valid


def styled_segments(text: str, annotations: list[dict[str, Any]]) -> list[tuple[str, list[dict]]]:
    """Split text at annotation boundaries so overlapping styles can be rendered per segment."""

    valid = normalized(text, annotations)
    boundaries = {0, len(text)}
    for annotation in valid:
        boundaries.update((annotation["start"], annotation["end"]))
    positions = sorted(boundaries)
    return [
        (
            text[start:end],
            [item for item in valid if item["start"] <= start and item["end"] >= end],
        )
        for start, end in zip(positions, positions[1:], strict=False)
        if start < end
    ]


def custom_tag_color(label: str) -> str:
    return CUSTOM_TAG_COLORS[sum(map(ord, label)) % len(CUSTOM_TAG_COLORS)]


def tag_color(label: str, stored: object = None) -> str:
    """Predefined tags always use their current color; custom tags keep their stored one."""

    if label in TAG_COLORS:
        return TAG_COLORS[label]
    if isinstance(stored, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", stored):
        return stored
    return custom_tag_color(label)


def tag_text_color(color: str) -> str:
    """A dark, readable shade of a pale tag color, used for its name label."""

    red, green, blue = (int(color[index:index + 2], 16) / 255 for index in (1, 3, 5))
    hue, _lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    red, green, blue = colorsys.hls_to_rgb(hue, 0.32, min(0.65, saturation))
    return "#{:02X}{:02X}{:02X}".format(*(round(value * 255) for value in (red, green, blue)))


def tag_spans(text: str, annotations: list[dict[str, Any]]) -> list[TagSpan]:
    """Return the tagged ranges in reading order; touching ranges of one label are merged."""

    tags = sorted(
        (item for item in normalized(text, annotations) if item["kind"] == "tag"),
        key=lambda item: (item["start"], item["end"]),
    )
    spans: list[TagSpan] = []
    for item in tags:
        label = str(item.get("label") or "Tag")
        color = tag_color(label, item.get("color"))
        if spans and spans[-1].label == label and spans[-1].end >= item["start"]:
            previous = spans.pop()
            start, end = previous.start, max(previous.end, item["end"])
        else:
            start, end = item["start"], item["end"]
        spans.append(TagSpan(label, start, end, text[start:end], color))
    return spans


def _readable(text: str) -> str:
    return " ".join(text.split())


def tag_summary(text: str, annotations: list[dict[str, Any]]) -> str:
    """Describe a line's tags as ``Person: Matthias Müller; Place: Wien``."""

    return "; ".join(
        f"{span.label}: {_readable(span.text)}" for span in tag_spans(text, annotations)
    )


def tag_label_html(label: str, color: str) -> str:
    """A small colored name label placed directly after a tagged word."""

    return (
        f'<span style="background-color:{tag_text_color(color)}; color:#FFFFFF; '
        f'font-size:small; font-weight:600;">&nbsp;{html.escape(label)}&nbsp;</span>'
    )


def annotated_html(text: str, annotations: list[dict[str, Any]]) -> str:
    """Render a line as rich text with formatting and each tag's name at its words."""

    ends: dict[int, list[TagSpan]] = {}
    for span in tag_spans(text, annotations):
        ends.setdefault(span.end, []).append(span)
    parts: list[str] = []
    position = 0
    for segment, active in styled_segments(text, annotations):
        position += len(segment)
        kinds = {str(item["kind"]) for item in active}
        piece = html.escape(segment).replace("\n", "<br>")
        tag = next((item for item in active if item["kind"] == "tag"), None)
        highlight = next((item for item in active if item["kind"] == "highlight"), None)
        if tag is not None:
            color = tag_color(str(tag.get("label") or "Tag"), tag.get("color"))
            piece = f'<span style="background-color:{color};">{piece}</span>'
        elif highlight is not None:
            piece = f'<span style="background-color:{HIGHLIGHT_COLOR};">{piece}</span>'
        if "superscript" in kinds:
            piece = f"<sup>{piece}</sup>"
        elif "subscript" in kinds:
            piece = f"<sub>{piece}</sub>"
        parts.append(piece)
        for span in ends.get(position, []):
            parts.append(tag_label_html(span.label, span.color))
    return "".join(parts)
