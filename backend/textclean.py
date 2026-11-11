"""Sanitising of untrusted feed text before it reaches the LLM prompt."""

import html
import re
from html.parser import HTMLParser

TITLE_MAX = 300
DESCRIPTION_MAX = 1000

_SKIPPED_TAGS = {"script", "style"}
_WHITESPACE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        else:
            self._parts.append(" ")

    def handle_endtag(self, tag):
        if tag in _SKIPPED_TAGS and self._skip_depth:
            self._skip_depth -= 1
        self._parts.append(" ")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


def clean_text(value: str | None, max_len: int) -> str:
    """Strip HTML, decode entities, collapse whitespace and truncate."""
    if not value:
        return ""
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = parser.text()
    except Exception:
        text = re.sub(r"<[^>]*>", " ", value)
    text = _WHITESPACE.sub(" ", html.unescape(text)).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text
