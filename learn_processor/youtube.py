from __future__ import annotations

import html
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from youtube_transcript_api import YouTubeTranscriptApi
from yt_dlp import YoutubeDL

from .common import MarkdownChunk, word_count


YOUTUBE_URL_RE = re.compile(r"https?://(?:www\.|m\.)?(?:youtube\.com|youtu\.be)/[^\s<>\]\[\"']+", re.I)


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    duration: float
    text: str


@dataclass(frozen=True)
class VideoExtraction:
    video_id: str
    url: str
    title: str
    channel: str | None
    duration: float | None
    transcript_source: str
    segments: tuple[TranscriptSegment, ...]


def extract_youtube_id(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().split(":", 1)[0]
    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        else:
            parts = [part for part in parsed.path.split("/") if part]
            candidate = parts[1] if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live"} else ""
    else:
        candidate = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
        raise ValueError(f"Not a supported YouTube video URL: {url}")
    return candidate


def parse_youtube_links(text: str) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for match in YOUTUBE_URL_RE.findall(line):
            cleaned = match.rstrip(".,);}")
            video_id = extract_youtube_id(cleaned)
            canonical = f"https://www.youtube.com/watch?v={video_id}"
            if canonical not in seen:
                seen.add(canonical)
                links.append(canonical)
    if not links:
        raise ValueError("The TXT file does not contain any valid YouTube video links.")
    return links


def _metadata(url: str, video_id: str) -> dict[str, object]:
    try:
        with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": str(info.get("title") or video_id),
            "channel": info.get("channel") or info.get("uploader"),
            "duration": info.get("duration"),
        }
    except Exception:
        return {"title": video_id, "channel": None, "duration": None}


def _caption_segments(video_id: str, languages: tuple[str, ...]) -> list[TranscriptSegment]:
    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=list(languages))
    except AttributeError:  # Compatibility with releases before the instance API.
        fetched = YouTubeTranscriptApi.get_transcript(video_id, languages=list(languages))
    segments: list[TranscriptSegment] = []
    previous = ""
    for cue in fetched:
        if isinstance(cue, dict):
            text, start, duration = cue["text"], cue["start"], cue.get("duration", 0.0)
        else:
            text, start, duration = cue.text, cue.start, cue.duration
        cleaned = re.sub(r"\s+", " ", html.unescape(str(text))).strip()
        if cleaned and cleaned != previous:
            segments.append(TranscriptSegment(float(start), float(duration), cleaned))
            previous = cleaned
    if not segments:
        raise ValueError("The available YouTube caption track was empty.")
    return segments


def _whisper_segments(url: str, model_name: str) -> list[TranscriptSegment]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Local transcription requires the faster-whisper package.") from exc

    with tempfile.TemporaryDirectory(prefix="learn-audio-") as temp_name:
        template = str(Path(temp_name) / "audio.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "outtmpl": template,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        with YoutubeDL(options) as ydl:
            ydl.download([url])
        candidates = [path for path in Path(temp_name).glob("audio.*") if path.is_file()]
        if not candidates:
            raise RuntimeError("YouTube audio could not be downloaded for local transcription.")
        model = WhisperModel(model_name, device="auto", compute_type="int8")
        generated, _info = model.transcribe(str(candidates[0]), vad_filter=True, beam_size=5)
        segments = [
            TranscriptSegment(float(item.start), float(item.end - item.start), item.text.strip())
            for item in generated
            if item.text.strip()
        ]
    if not segments:
        raise ValueError("Local transcription produced no spoken content.")
    return segments


def extract_video(
    url: str,
    languages: tuple[str, ...],
    whisper_fallback: bool,
    whisper_model: str,
) -> VideoExtraction:
    video_id = extract_youtube_id(url)
    metadata = _metadata(url, video_id)
    try:
        segments = _caption_segments(video_id, languages)
        source = "youtube_captions"
    except Exception as caption_error:
        if not whisper_fallback:
            raise RuntimeError(f"Captions unavailable: {caption_error}") from caption_error
        try:
            segments = _whisper_segments(url, whisper_model)
            source = f"faster_whisper:{whisper_model}"
        except Exception as whisper_error:
            raise RuntimeError(
                f"Captions unavailable ({caption_error}); local transcription failed ({whisper_error})."
            ) from whisper_error
    return VideoExtraction(
        video_id=video_id,
        url=url,
        title=str(metadata["title"]),
        channel=str(metadata["channel"]) if metadata["channel"] else None,
        duration=float(metadata["duration"]) if metadata["duration"] is not None else None,
        transcript_source=source,
        segments=tuple(segments),
    )


def format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def _timestamp_buckets(
    segments: tuple[TranscriptSegment, ...], interval_seconds: int
) -> list[tuple[float, str]]:
    buckets: list[tuple[float, list[str]]] = []
    current_bucket: int | None = None
    for segment in segments:
        bucket = int(math.floor(segment.start / interval_seconds))
        if current_bucket != bucket:
            buckets.append((segment.start, []))
            current_bucket = bucket
        buckets[-1][1].append(segment.text)
    return [(start, " ".join(texts)) for start, texts in buckets]


def transcript_chunks(
    video: VideoExtraction,
    target_words: int,
    overlap_words: int,
    interval_seconds: int,
) -> list[MarkdownChunk]:
    units = _timestamp_buckets(video.segments, interval_seconds)
    chunks: list[MarkdownChunk] = []
    start = 0
    while start < len(units):
        end = start
        count = 0
        while end < len(units) and (count < target_words or end == start):
            count += word_count(units[end][1])
            end += 1
        selected = units[start:end]
        body_parts = []
        for timestamp, spoken_text in selected:
            second = int(timestamp)
            linked_url = f"https://www.youtube.com/watch?v={video.video_id}&t={second}s"
            body_parts.append(f"**[{format_time(timestamp)}]({linked_url})**  \n{spoken_text}")
        number = len(chunks) + 1
        chunks.append(
            MarkdownChunk(
                number=number,
                title=f"Transcript {format_time(selected[0][0])} to {format_time(selected[-1][0])}",
                body="\n\n".join(body_parts) + "\n",
                word_count=sum(word_count(text) for _, text in selected),
                source_refs=(
                    f"{format_time(selected[0][0])}-{format_time(selected[-1][0])}",
                ),
            )
        )
        if end >= len(units):
            break
        carried = 0
        next_start = end
        while next_start > start and carried < overlap_words:
            next_start -= 1
            carried += word_count(units[next_start][1])
        start = next_start if next_start > start else end
    return chunks
