from textclean import clean_text


def test_strips_html_tags_and_decodes_entities():
    raw = '<p>Heavy <b>rain</b> &amp; wind hit <a href="https://x">Tokyo</a></p><img src="x.png"/>'
    assert clean_text(raw, 500) == "Heavy rain & wind hit Tokyo"


def test_drops_script_and_style_content():
    raw = "Before<script>alert('x')</script><style>p{color:red}</style>After"
    text = clean_text(raw, 500)
    assert "alert" not in text and "color" not in text
    assert "Before" in text and "After" in text


def test_collapses_whitespace():
    assert clean_text("a \n\n  b\t c", 100) == "a b c"


def test_truncates_with_ellipsis():
    text = clean_text("x" * 50, 10)
    assert len(text) == 10 and text.endswith("…")


def test_none_and_empty():
    assert clean_text(None, 10) == ""
    assert clean_text("", 10) == ""


def test_malformed_html_does_not_raise():
    assert "text" in clean_text("<div <<p> text </", 100)
