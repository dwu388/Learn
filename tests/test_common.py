from learn_processor.common import (
    MarkdownSection,
    chunk_sections,
    safe_name,
    unique_file_destination,
)


def test_safe_name_is_filesystem_friendly():
    assert safe_name("A Book: Déjà Vu?!") == "a-book-deja-vu"
    assert safe_name("CON") == "source-con"


def test_chunk_sections_preserves_all_content_and_overlap_progresses():
    sections = [
        MarkdownSection("One", "alpha beta gamma\n\ndelta epsilon zeta", "page 1"),
        MarkdownSection("Two", "eta theta iota\n\nkappa lambda mu", "page 2"),
    ]
    chunks = chunk_sections(sections, target_words=6, overlap_words=2)
    assert len(chunks) >= 2
    assert "alpha beta gamma" in chunks[0].body
    assert "kappa lambda mu" in chunks[-1].body
    assert all(chunk.word_count > 0 for chunk in chunks)


def test_oversized_paragraph_is_bounded_and_keeps_section_context():
    section = MarkdownSection("Long Section", " ".join(f"word{number}" for number in range(700)))
    chunks = chunk_sections([section], target_words=250, overlap_words=0)
    assert len(chunks) == 3
    assert all(chunk.word_count <= 250 for chunk in chunks)
    assert all(chunk.body.startswith("## Long Section") for chunk in chunks)


def test_unique_file_destination_versions_existing_file(tmp_path):
    (tmp_path / "links.txt").write_text("existing", encoding="utf-8")
    assert unique_file_destination(tmp_path, "links", ".txt").name == "links-v2.txt"
