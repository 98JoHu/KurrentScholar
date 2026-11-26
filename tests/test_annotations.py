from kurrentscholar.annotations import (
    TAG_COLORS,
    annotated_html,
    styled_segments,
    tag_color,
    tag_spans,
    tag_summary,
    tag_text_color,
)

TEXT = "Matthias Müller zu Wien"
TAGS = [
    {"start": 0, "end": 8, "kind": "tag", "label": "Person", "color": "#F2C7C3"},
    {"start": 8, "end": 15, "kind": "tag", "label": "Person", "color": "#F2C7C3"},
    {"start": 19, "end": 23, "kind": "tag", "label": "Place", "color": "#C9DDF7"},
]


def test_touching_ranges_of_one_tag_form_one_span():
    spans = tag_spans(TEXT, TAGS)
    assert [(span.label, span.text) for span in spans] == [
        ("Person", "Matthias Müller"),
        ("Place", "Wien"),
    ]
    assert tag_summary(TEXT, TAGS) == "Person: Matthias Müller; Place: Wien"


def test_malformed_and_out_of_range_annotations_are_ignored_or_clamped():
    annotations = [
        {"start": "x", "end": 3, "kind": "tag"},
        {"start": 2, "kind": "tag"},
        {"start": 5, "end": 5, "kind": "tag", "label": "Empty"},
        {"start": 19, "end": 400, "kind": "tag", "label": "Place"},
    ]
    assert [(span.label, span.text) for span in tag_spans(TEXT, annotations)] == [("Place", "Wien")]
    assert "".join(segment for segment, _ in styled_segments(TEXT, annotations)) == TEXT


def test_html_names_each_tag_directly_after_its_words_and_escapes_text():
    markup = annotated_html("<b>Wien</b> & mehr", [
        {"start": 3, "end": 7, "kind": "tag", "label": "Place<script>"},
        {"start": 0, "end": 3, "kind": "superscript"},
    ])
    assert "<b>" not in markup and "&lt;b&gt;" in markup
    assert "Place&lt;script&gt;" in markup and "<script>" not in markup
    assert markup.index("Wien") < markup.index("Place&lt;script&gt;") < markup.index("mehr")
    assert "<sup>" in markup


def test_predefined_tags_use_current_colors_and_custom_tags_are_stable():
    assert tag_color("Unclear", "#FFE7A8") == TAG_COLORS["Unclear"]
    assert tag_color("Kirche", "#123456") == "#123456"
    assert tag_color("Kirche", None) == tag_color("Kirche", "not a color")
    assert tag_color("Kirche") not in TAG_COLORS.values()
    dark = tag_text_color(TAG_COLORS["Place"])
    assert dark.startswith("#") and len(dark) == 7 and dark != TAG_COLORS["Place"]
