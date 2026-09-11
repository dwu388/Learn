from unittest.mock import Mock, patch

import pytest

from learn_processor.youtube import (
    TranscriptSegment,
    VideoExtraction,
    _ydl_options,
    detect_javascript_runtime,
    extract_video,
    extract_youtube_id,
    parse_youtube_links,
    transcript_chunks,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=5", "dQw4w9WgXcQ"),
        ("https://youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_youtube_id(url, expected):
    assert extract_youtube_id(url) == expected


def test_parse_youtube_links_deduplicates_and_ignores_comments():
    text = """
    # https://youtu.be/aaaaaaaaaaa
    First https://youtu.be/dQw4w9WgXcQ
    https://www.youtube.com/watch?v=dQw4w9WgXcQ
    https://youtube.com/watch?v=9bZkp7q19f0
    """
    assert parse_youtube_links(text) == [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=9bZkp7q19f0",
    ]


def test_transcript_chunks_include_clickable_timestamps():
    video = VideoExtraction(
        video_id="dQw4w9WgXcQ",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        title="Example",
        channel="Channel",
        duration=120,
        transcript_source="test",
        javascript_runtime=None,
        segments=(
            TranscriptSegment(0, 10, "first spoken sentence"),
            TranscriptSegment(65, 10, "second spoken sentence"),
        ),
    )
    chunks = transcript_chunks(video, target_words=100, overlap_words=0, interval_seconds=60)
    assert len(chunks) == 1
    assert "[00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s)" in chunks[0].body
    assert "[01:05](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=65s)" in chunks[0].body


def test_runtime_detection_accepts_deno_2_and_prefers_it():
    completed = Mock(returncode=0, stdout="deno 2.4.0\n")
    with (
        patch("learn_processor.youtube.shutil.which", return_value="C:/deno/deno.exe"),
        patch("learn_processor.youtube.subprocess.run", return_value=completed),
    ):
        assert detect_javascript_runtime() == ("deno", "C:/deno/deno.exe")


def test_runtime_detection_rejects_old_versions():
    completed = Mock(returncode=0, stdout="v18.20.0\n")
    with (
        patch(
            "learn_processor.youtube.shutil.which",
            side_effect=lambda name: None if name == "deno" else "C:/node/node.exe",
        ),
        patch("learn_processor.youtube.subprocess.run", return_value=completed),
    ):
        assert detect_javascript_runtime() is None


def test_node_runtime_is_passed_to_ytdlp():
    options = _ydl_options(("node", "C:/node/node.exe"), skip_download=True)
    assert options["js_runtimes"] == {"node": {"path": "C:/node/node.exe"}}
    assert options["skip_download"] is True


def test_whisper_fallback_receives_selected_device():
    fallback = [TranscriptSegment(0, 5, "locally transcribed")]
    with (
        patch("learn_processor.youtube.detect_javascript_runtime", return_value=None),
        patch(
            "learn_processor.youtube._metadata",
            return_value={"title": "Video", "channel": "Channel", "duration": 5},
        ),
        patch("learn_processor.youtube._caption_segments", side_effect=RuntimeError("none")),
        patch("learn_processor.youtube._whisper_segments", return_value=fallback) as whisper,
    ):
        result = extract_video(
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ("en",),
            True,
            "small",
            "cpu",
        )
    whisper.assert_called_once_with(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "small", "cpu", None
    )
    assert result.transcript_source == "faster_whisper:small"
