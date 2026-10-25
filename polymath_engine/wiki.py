"""Read individual articles from an existing offline Wikipedia ZIM archive."""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Article:
    title: str
    path: str
    text: str
    archive: str

    @property
    def source_id(self) -> str:
        return f"zim:{self.archive}:{self.path}"


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select(
        "script, style, nav, footer, noscript, sup.reference, "
        ".reflist, .references, .mw-editsection, .navbox, .toc"
    ):
        tag.decompose()
    root = soup.select_one("#mw-content-text") or soup.select_one("article") or soup.body or soup
    return "\n".join(line for line in (
        unescape(part).strip() for part in root.get_text("\n").splitlines()
    ) if line)


class ZimWikipedia:
    """Direct ZIM access; does not require a Kiwix server or another archive copy."""

    def __init__(self, filename: Path):
        self.filename = Path(filename).expanduser().resolve()
        if not self.filename.is_file():
            raise FileNotFoundError(f"Wikipedia ZIM not found: {self.filename}")
        try:
            from libzim.reader import Archive
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional ZIM reader: python -m pip install libzim"
            ) from exc
        self.archive = Archive(str(self.filename))

    def get(self, title: str) -> Article:
        try:
            entry = self.archive.get_entry_by_title(title)
        except KeyError:
            # Older ZIMs may index URL paths rather than display titles.
            entry = self.archive.get_entry_by_path("A/" + title.replace(" ", "_"))
        for _ in range(8):
            if not entry.is_redirect:
                break
            entry = entry.get_redirect_entry()
        else:
            raise ValueError(f"Redirect loop for {title}")
        item = entry.get_item()
        if "html" not in str(item.mimetype).lower():
            raise ValueError(f"Entry is not HTML: {title} ({item.mimetype})")
        text = html_to_text(bytes(item.content).decode("utf-8", errors="replace"))
        if not text:
            raise ValueError(f"No readable article text for {title}")
        return Article(
            title=entry.title, path=entry.path, text=text, archive=self.filename.name
        )
