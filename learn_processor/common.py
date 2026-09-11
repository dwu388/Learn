from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class MarkdownSection:
    title: str
    body: str
    source_ref: str | None = None


@dataclass(frozen=True)
class MarkdownChunk:
    number: int
    title: str
    body: str
    word_count: int
    source_refs: tuple[str, ...]


def safe_name(value: str, fallback: str = "source") -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._").lower()
    return cleaned[:100] or fallback


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+(?:['’-]\w+)*\b", text, flags=re.UNICODE))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def yaml_value(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def front_matter(items: dict[str, object]) -> str:
    lines = ["---"]
    lines.extend(f"{key}: {yaml_value(value)}" for key, value in items.items() if value is not None)
    lines.extend(["---", ""])
    return "\n".join(lines)


def split_paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def chunk_sections(
    sections: Sequence[MarkdownSection], target_words: int, overlap_words: int
) -> list[MarkdownChunk]:
    """Chunk at paragraph boundaries while retaining section labels and provenance."""
    if target_words <= 0 or overlap_words < 0 or overlap_words >= target_words:
        raise ValueError("Chunk sizes must satisfy 0 <= overlap_words < target_words.")

    units: list[tuple[str, str | None, str]] = []
    for section in sections:
        paragraphs = split_paragraphs(section.body)
        if not paragraphs:
            continue
        for index, paragraph in enumerate(paragraphs):
            units.append((section.title if index == 0 else "", section.source_ref, paragraph))

    chunks: list[MarkdownChunk] = []
    start = 0
    while start < len(units):
        end = start
        count = 0
        while end < len(units) and (count < target_words or end == start):
            count += word_count(units[end][2])
            end += 1

        selected = units[start:end]
        body_parts: list[str] = []
        current_title = ""
        refs: list[str] = []
        for title, source_ref, paragraph in selected:
            if title:
                current_title = title
                body_parts.append(f"## {title}")
            if source_ref and source_ref not in refs:
                refs.append(source_ref)
            body_parts.append(paragraph)

        chunk_number = len(chunks) + 1
        chunks.append(
            MarkdownChunk(
                number=chunk_number,
                title=current_title or f"Chunk {chunk_number}",
                body="\n\n".join(body_parts).strip() + "\n",
                word_count=sum(word_count(item[2]) for item in selected),
                source_refs=tuple(refs),
            )
        )
        if end >= len(units):
            break

        carried = 0
        next_start = end
        while next_start > start and carried < overlap_words:
            next_start -= 1
            carried += word_count(units[next_start][2])
        start = next_start if next_start > start else end

    return chunks


def unique_destination(root: Path, stem: str) -> Path:
    candidate = root / safe_name(stem)
    if not candidate.exists():
        return candidate
    version = 2
    while True:
        candidate = root / f"{safe_name(stem)}-v{version}"
        if not candidate.exists():
            return candidate
        version += 1


def unique_file_destination(root: Path, stem: str, suffix: str) -> Path:
    normalized_stem = safe_name(stem)
    candidate = root / f"{normalized_stem}{suffix}"
    if not candidate.exists():
        return candidate
    version = 2
    while True:
        candidate = root / f"{normalized_stem}-v{version}{suffix}"
        if not candidate.exists():
            return candidate
        version += 1


def write_chunks(
    source_dir: Path,
    chunks: Iterable[MarkdownChunk],
    metadata: dict[str, object],
) -> tuple[int, int, list[dict[str, object]]]:
    chunk_dir = source_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=False)
    records: list[dict[str, object]] = []
    total_words = 0
    chunk_list = list(chunks)
    width = max(3, len(str(len(chunk_list))))
    for chunk in chunk_list:
        filename = f"chunk-{chunk.number:0{width}d}.md"
        document = front_matter(
            {
                **metadata,
                "chunk": chunk.number,
                "word_count": chunk.word_count,
                "source_refs": list(chunk.source_refs),
            }
        )
        document += f"# {metadata.get('title', 'Untitled')}\n\n{chunk.body}"
        (chunk_dir / filename).write_text(document, encoding="utf-8", newline="\n")
        records.append(
            {
                "file": f"chunks/{filename}",
                "title": chunk.title,
                "word_count": chunk.word_count,
                "source_refs": list(chunk.source_refs),
            }
        )
        total_words += chunk.word_count
    return len(chunk_list), total_words, records
