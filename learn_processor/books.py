from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import ebooklib
import pymupdf
from bs4 import BeautifulSoup
from ebooklib import epub
from markdownify import markdownify

from .common import MarkdownSection


@dataclass(frozen=True)
class BookExtraction:
    title: str
    author: str | None
    format: str
    sections: tuple[MarkdownSection, ...]
    page_count: int | None = None


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf(path: Path) -> BookExtraction:
    with pymupdf.open(path) as document:
        metadata = document.metadata or {}
        title = (metadata.get("title") or path.stem).strip()
        author = (metadata.get("author") or "").strip() or None
        pages = [_clean_text(page.get_text("text", sort=True)) for page in document]
        non_space_characters = sum(len(re.sub(r"\s", "", page)) for page in pages)
        if non_space_characters < max(100, len(document) * 20):
            raise ValueError(
                "The PDF does not contain enough searchable text. OCR-only PDFs are intentionally unsupported."
            )

        toc = [entry for entry in document.get_toc(simple=True) if len(entry) >= 3]
        sections: list[MarkdownSection] = []
        if toc:
            top_level = min(int(entry[0]) for entry in toc)
            entries = [entry for entry in toc if int(entry[0]) == top_level]
            first_toc_page = max(0, int(entries[0][2]) - 1)
            if first_toc_page > 0:
                front_pages = [
                    f"<!-- page: {page_index + 1} -->\n\n{pages[page_index]}"
                    for page_index in range(first_toc_page)
                    if pages[page_index]
                ]
                if front_pages:
                    sections.append(
                        MarkdownSection(
                            title="Front Matter",
                            body="\n\n".join(front_pages),
                            source_ref=f"pages 1-{first_toc_page}",
                        )
                    )
            for index, entry in enumerate(entries):
                start_page = max(0, int(entry[2]) - 1)
                end_page = max(start_page + 1, int(entries[index + 1][2]) - 1) if index + 1 < len(entries) else len(pages)
                body_parts = []
                for page_index in range(start_page, min(end_page, len(pages))):
                    if pages[page_index]:
                        body_parts.append(f"<!-- page: {page_index + 1} -->\n\n{pages[page_index]}")
                if body_parts:
                    sections.append(
                        MarkdownSection(
                            title=_clean_text(str(entry[1])) or f"Page {start_page + 1}",
                            body="\n\n".join(body_parts),
                            source_ref=f"pages {start_page + 1}-{min(end_page, len(pages))}",
                        )
                    )
        else:
            sections = [
                MarkdownSection(
                    title=f"Page {number}",
                    body=f"<!-- page: {number} -->\n\n{text}",
                    source_ref=f"page {number}",
                )
                for number, text in enumerate(pages, start=1)
                if text
            ]

        return BookExtraction(
            title=title,
            author=author,
            format="pdf",
            sections=tuple(sections),
            page_count=len(pages),
        )


def _epub_metadata(book: epub.EpubBook, field: str) -> str | None:
    values = book.get_metadata("DC", field)
    if not values:
        return None
    value = str(values[0][0]).strip()
    return value or None


def extract_epub(path: Path) -> BookExtraction:
    book = epub.read_epub(str(path), options={"ignore_ncx": True})
    title = _epub_metadata(book, "title") or path.stem
    author = _epub_metadata(book, "creator")
    item_by_id = {item.get_id(): item for item in book.get_items()}
    ordered_items = []
    seen: set[str] = set()
    for item_id, _linear in book.spine:
        item = item_by_id.get(item_id)
        if item is not None and item.get_type() == ebooklib.ITEM_DOCUMENT:
            ordered_items.append(item)
            seen.add(item.get_id())
    ordered_items.extend(
        item for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT) if item.get_id() not in seen
    )

    sections: list[MarkdownSection] = []
    for number, item in enumerate(ordered_items, start=1):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for unwanted in soup(["script", "style", "svg"]):
            unwanted.decompose()
        heading = soup.find(["h1", "h2", "h3", "title"])
        section_title = heading.get_text(" ", strip=True) if heading else f"Section {number}"
        body = markdownify(str(soup.body or soup), heading_style="ATX", bullets="-")
        body = _clean_text(body)
        if body:
            sections.append(
                MarkdownSection(
                    title=section_title,
                    body=body,
                    source_ref=f"EPUB item {number}: {item.get_name()}",
                )
            )
    if not sections:
        raise ValueError("No readable document sections were found in the EPUB.")
    return BookExtraction(title=title, author=author, format="epub", sections=tuple(sections))


def extract_book(path: Path) -> BookExtraction:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".epub":
        return extract_epub(path)
    raise ValueError(f"Unsupported book format: {suffix}")
