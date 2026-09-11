from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .books import extract_book
from .common import (
    chunk_sections,
    front_matter,
    safe_name,
    sha256_file,
    unique_destination,
    unique_file_destination,
    write_chunks,
)
from .youtube import extract_video, parse_youtube_links, transcript_chunks


@dataclass(frozen=True)
class ProcessingOptions:
    output_dir: Path
    chunk_words: int = 1200
    overlap_words: int = 120
    timestamp_interval: int = 60
    languages: tuple[str, ...] = ("en", "en-US", "en-GB")
    copy_originals: bool = True
    whisper_fallback: bool = True
    whisper_model: str = "small"
    whisper_device: str = "cpu"


@dataclass(frozen=True)
class ProcessingResult:
    label: str
    success: bool
    output_path: Path | None = None
    chunk_count: int = 0
    word_count: int = 0
    error: str | None = None


ProgressCallback = Callable[[int, int, str], None]


def _write_index(
    directory: Path, metadata: dict[str, object], records: list[dict[str, object]]
) -> None:
    lines = [front_matter(metadata), f"# {metadata['title']}", ""]
    if metadata.get("source_url"):
        lines.extend([f"Original: {metadata['source_url']}", ""])
    lines.extend(["## Chunks", ""])
    for record in records:
        lines.append(f"- [{record['title']}]({record['file']}) ({record['word_count']} words)")
    (directory / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (directory / "manifest.json").write_text(
        json.dumps({**metadata, "chunks": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _finalize(staging: Path, destination: Path) -> Path:
    staging.replace(destination)
    return destination


def _process_book(path: Path, original_name: str, options: ProcessingOptions) -> ProcessingResult:
    book = extract_book(path)
    chunks = chunk_sections(book.sections, options.chunk_words, options.overlap_words)
    if not chunks:
        raise ValueError("No readable text remained after extraction.")
    destination = unique_destination(options.output_dir, book.title)
    staging = Path(tempfile.mkdtemp(prefix=".learn-book-", dir=options.output_dir))
    try:
        metadata: dict[str, object] = {
            "schema_version": 1,
            "source_type": book.format,
            "source_file": original_name,
            "source_sha256": sha256_file(path),
            "title": book.title,
            "author": book.author,
            "page_count": book.page_count,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "chunk_target_words": options.chunk_words,
            "chunk_overlap_words": options.overlap_words,
        }
        chunk_count, total_words, records = write_chunks(staging, chunks, metadata)
        if options.copy_originals:
            original_dir = staging / "original"
            original_dir.mkdir()
            archived_name = (
                f"{safe_name(Path(original_name).stem, 'book')}{Path(original_name).suffix.lower()}"
            )
            shutil.copy2(path, original_dir / archived_name)
        _write_index(staging, metadata, records)
        return ProcessingResult(
            book.title, True, _finalize(staging, destination), chunk_count, total_words
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _process_video(url: str, options: ProcessingOptions) -> ProcessingResult:
    video = extract_video(
        url,
        options.languages,
        options.whisper_fallback,
        options.whisper_model,
        options.whisper_device,
    )
    chunks = transcript_chunks(
        video, options.chunk_words, options.overlap_words, options.timestamp_interval
    )
    destination = unique_destination(options.output_dir, f"{video.title}-{video.video_id}")
    staging = Path(tempfile.mkdtemp(prefix=".learn-video-", dir=options.output_dir))
    try:
        metadata: dict[str, object] = {
            "schema_version": 1,
            "source_type": "youtube",
            "source_url": video.url,
            "video_id": video.video_id,
            "title": video.title,
            "channel": video.channel,
            "duration_seconds": video.duration,
            "transcript_source": video.transcript_source,
            "javascript_runtime": video.javascript_runtime,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "chunk_target_words": options.chunk_words,
            "chunk_overlap_words": options.overlap_words,
            "timestamp_interval_seconds": options.timestamp_interval,
        }
        chunk_count, total_words, records = write_chunks(staging, chunks, metadata)
        _write_index(staging, metadata, records)
        return ProcessingResult(
            video.title, True, _finalize(staging, destination), chunk_count, total_words
        )
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _write_catalog(output_dir: Path) -> None:
    entries: list[dict[str, object]] = []
    for directory in output_dir.iterdir():
        if not directory.is_dir() or directory.name.startswith(".") or directory.name == "_inputs":
            continue
        manifest_path = directory / "manifest.json"
        index_path = directory / "index.md"
        if not manifest_path.is_file() or not index_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            records = manifest.get("chunks", [])
            entries.append(
                {
                    "title": str(manifest.get("title") or directory.name).replace("\n", " "),
                    "directory": directory.name,
                    "chunk_count": len(records),
                    "word_count": sum(int(record.get("word_count", 0)) for record in records),
                }
            )
        except (OSError, ValueError, TypeError):
            continue
    entries.sort(key=lambda item: (str(item["title"]).casefold(), str(item["directory"])))
    lines = [
        "# Learn Markdown Library",
        "",
        f"Updated: {datetime.now(timezone.utc).isoformat()}",
        "",
    ]
    for item in entries:
        lines.append(
            f"- [{item['title']}]({item['directory']}/index.md) "
            f"({item['chunk_count']} chunks, {item['word_count']} words)"
        )
    catalog = output_dir / "catalog.md"
    temporary = output_dir / ".catalog.md.tmp"
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(catalog)


def process_files(
    uploads: Iterable[tuple[Path, str]],
    options: ProcessingOptions,
    progress: ProgressCallback | None = None,
) -> list[ProcessingResult]:
    if (
        options.chunk_words <= 0
        or options.overlap_words < 0
        or options.overlap_words >= options.chunk_words
    ):
        raise ValueError("Chunk sizes must satisfy 0 <= overlap_words < chunk_words.")
    if options.timestamp_interval <= 0:
        raise ValueError("Timestamp interval must be positive.")
    if options.whisper_model not in {"tiny", "base", "small", "medium"}:
        raise ValueError("Unsupported Whisper model.")
    if options.whisper_device not in {"cpu", "cuda"}:
        raise ValueError("Whisper device must be 'cpu' or 'cuda'.")
    options.output_dir.mkdir(parents=True, exist_ok=True)
    upload_list = list(uploads)
    results: list[ProcessingResult] = []
    for number, (path, original_name) in enumerate(upload_list, start=1):
        suffix = Path(original_name).suffix.lower()
        try:
            if suffix in {".pdf", ".epub"}:
                results.append(_process_book(path, original_name, options))
            elif suffix == ".txt":
                text = path.read_text(encoding="utf-8-sig")
                links = parse_youtube_links(text)
                if options.copy_originals:
                    input_dir = options.output_dir / "_inputs"
                    input_dir.mkdir(exist_ok=True)
                    destination = unique_file_destination(
                        input_dir, Path(original_name).stem, ".txt"
                    )
                    shutil.copy2(path, destination)
                for url in links:
                    try:
                        results.append(_process_video(url, options))
                    except Exception as exc:
                        results.append(ProcessingResult(url, False, error=str(exc)))
            else:
                raise ValueError(f"Unsupported file type: {suffix or '(none)'}")
        except Exception as exc:
            results.append(ProcessingResult(original_name, False, error=str(exc)))
        if progress:
            progress(number, len(upload_list), f"Finished {original_name}")
    _write_catalog(options.output_dir)
    return results
