import json

import pymupdf
from ebooklib import epub

from learn_processor.books import extract_epub, extract_pdf
from learn_processor.pipeline import ProcessingOptions, process_files


def make_searchable_pdf(path):
    document = pymupdf.open()
    first = document.new_page()
    first.insert_text((72, 72), "Copyright and front matter. " * 4)
    second = document.new_page()
    second.insert_text((72, 72), "Chapter One searchable content. " * 4)
    document.set_metadata({"title": "Test PDF", "author": "Test Author"})
    document.set_toc([[1, "Chapter One", 2]])
    document.save(path)
    document.close()


def make_epub(path):
    book = epub.EpubBook()
    book.set_identifier("test-book")
    book.set_title("Test EPUB")
    book.add_author("Test Author")
    chapter = epub.EpubHtml(title="Opening", file_name="opening.xhtml", lang="en")
    chapter.content = "<html><body><h1>Opening</h1><p>Readable EPUB content.</p></body></html>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(path, book)


def test_pdf_extraction_preserves_front_matter_and_page_markers(tmp_path):
    path = tmp_path / "book.pdf"
    make_searchable_pdf(path)
    extracted = extract_pdf(path)
    assert extracted.title == "Test PDF"
    assert extracted.page_count == 2
    assert extracted.sections[0].title == "Front Matter"
    assert "<!-- page: 1 -->" in extracted.sections[0].body
    assert "<!-- page: 2 -->" in extracted.sections[1].body


def test_epub_extraction_uses_spine_order(tmp_path):
    path = tmp_path / "book.epub"
    make_epub(path)
    extracted = extract_epub(path)
    assert extracted.title == "Test EPUB"
    assert extracted.author == "Test Author"
    assert "Readable EPUB content" in extracted.sections[0].body


def test_pipeline_writes_index_manifest_chunks_and_original(tmp_path):
    source = tmp_path / "source.pdf"
    output = tmp_path / "output"
    make_searchable_pdf(source)
    results = process_files(
        [(source, "Original Book.pdf")],
        ProcessingOptions(output_dir=output, chunk_words=250, overlap_words=0),
    )
    assert len(results) == 1
    assert results[0].success
    destination = results[0].output_path
    assert destination is not None
    assert (destination / "index.md").exists()
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_sha256"]
    assert len(manifest["chunks"]) == results[0].chunk_count
    assert (destination / "original" / "original-book.pdf").exists()
    assert "Test PDF" in (output / "catalog.md").read_text(encoding="utf-8")
