import re
from html.parser import HTMLParser


class _ReadableTextParser(HTMLParser):
    _ignored_tags = {"script", "style", "noscript", "template"}
    _block_tags = {"article", "div", "main", "p", "section"}
    _heading_prefixes = {f"h{level}": "#" * level for level in range(1, 7)}

    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.lines: list[str] = []
        self._current = ""
        self._ignored_depth = 0
        self._in_title = False
        self._link_href: str | None = None
        self._needs_space = False
        self._list_item_depth = 0
        self._strong_depth = 0
        self._emphasis_depth = 0

    def _flush(self) -> None:
        line = re.sub(r"\s+", " ", self._current).strip()
        if line:
            self.lines.append(line)
        self._current = ""

    def _append(self, value: str) -> None:
        if (
            self._needs_space
            and self._current
            and not self._current.endswith(" ")
            and not value.startswith(("]", ")", ",", ".", ":", ";", "!", "?"))
        ):
            self._current += " "
        self._needs_space = False
        if (
            self._current
            and not self._current.endswith((" ", "[", "**", "_"))
            and not value.startswith(("]", ")", ",", ".", ":", ";", "!", "?"))
            and value not in {"**", "_"}
        ):
            self._current += " "
        self._current += value

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = True
        elif tag in self._block_tags or tag in self._heading_prefixes:
            if tag == "p" and self._list_item_depth and self._current.strip() == "-":
                return
            self._flush()
            if tag in self._heading_prefixes:
                self._current = f"{self._heading_prefixes[tag]} "
        elif tag == "li":
            self._flush()
            self._current = "- "
            self._list_item_depth += 1
        elif tag in {"strong", "b"}:
            if self._strong_depth == 0:
                if self._current and not self._current.endswith((" ", "[", "(")):
                    self._current += " "
                self._current += "**"
            self._strong_depth += 1
        elif tag in {"em", "i"}:
            if self._emphasis_depth == 0:
                if self._current and not self._current.endswith((" ", "[", "(")):
                    self._current += " "
                self._current += "_"
            self._emphasis_depth += 1
        elif tag == "a":
            self._append("[")
            self._link_href = next((value for name, value in attrs if name == "href"), None)

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "li":
            self._flush()
            self._list_item_depth = max(0, self._list_item_depth - 1)
        elif tag in self._block_tags or tag in self._heading_prefixes:
            if tag == "p" and self._list_item_depth:
                return
            self._flush()
        elif tag in {"strong", "b"}:
            self._strong_depth = max(0, self._strong_depth - 1)
            if self._strong_depth == 0:
                self._current += "**"
                self._needs_space = True
        elif tag in {"em", "i"}:
            self._emphasis_depth = max(0, self._emphasis_depth - 1)
            if self._emphasis_depth == 0:
                self._current += "_"
                self._needs_space = True
        elif tag == "a":
            self._append(f"]({self._link_href})" if self._link_href else "]")
            self._link_href = None
            self._needs_space = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br" and not self._ignored_depth:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self._append(text)


def html_to_markdown(content: bytes) -> tuple[str | None, str]:
    parser = _ReadableTextParser()
    parser.feed(content.decode("utf-8", errors="replace"))
    parser._flush()
    title = " ".join(parser.title_parts).strip() or None
    markdown = "\n\n".join(parser.lines)
    if not markdown:
        raise ValueError("URL did not contain readable text")
    return title, markdown