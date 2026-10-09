from html.parser import HTMLParser


class _ReadableTextParser(HTMLParser):
    _ignored_tags = {"script", "style", "noscript", "template"}

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._ignored_tags:
            self._ignored_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def html_to_markdown(content: bytes) -> tuple[str | None, str]:
    parser = _ReadableTextParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    title = " ".join(parser.title_parts).strip() or None
    markdown = "\n\n".join(parser.text_parts)
    if not markdown:
        raise ValueError("URL did not contain readable text")
    return title, markdown