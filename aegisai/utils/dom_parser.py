"""DOM subset parsing.

The parser preserves structural attributes needed for healing. Secret-bearing
values such as input ``value`` are intentionally not captured; LLM/log redaction
is handled by ``aegisai.security``.
"""

from __future__ import annotations

from html.parser import HTMLParser

from aegisai.models import DomElement

ALLOWED_ATTRIBUTES = {
    "id",
    "name",
    "aria-label",
    "aria-labelledby",
    "aria-describedby",
    "data-testid",
    "role",
    "type",
    "placeholder",
    "autocomplete",
}

VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class _DomSubsetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[DomElement] = []
        self._stack: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        filtered = {
            key.lower(): value or ""
            for key, value in attrs
            if key.lower() in ALLOWED_ATTRIBUTES
        }
        role = filtered.get("role") or _implicit_role(tag, filtered)
        node = {
            "tag": tag,
            "attrs": filtered,
            "text": [],
            "role": role,
            "index": len(self.elements),
        }
        if tag.lower() in VOID_ELEMENTS:
            self._emit(node)
        else:
            self._stack.append(node)

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = data.strip()
        if text:
            self._stack[-1]["text"].append(text)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack:
            return
        current = self._stack.pop()
        if current["tag"] == tag:
            self._emit(current)

    def _emit(self, node: dict[str, object]) -> None:
        attrs = dict(node["attrs"])
        text = " ".join(node["text"])[:120]
        if not attrs and not text:
            return
        self.elements.append(
            DomElement(
                tag=str(node["tag"]),
                attrs=attrs,
                text=text,
                role=str(node["role"]) if node["role"] else None,
                index=int(node["index"]),
                path=f"{node['tag']}[{node['index']}]",
            )
        )


def parse_dom_subset(html: str) -> list[DomElement]:
    parser = _DomSubsetParser()
    parser.feed(html)
    return parser.elements


def _implicit_role(tag: str, attrs: dict[str, str]) -> str | None:
    if tag == "button":
        return "button"
    if tag == "a" and attrs.get("href"):
        return "link"
    if tag == "input":
        input_type = attrs.get("type", "text")
        if input_type in {"submit", "button"}:
            return "button"
        return "textbox"
    return None
