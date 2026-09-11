import pytest

from learn_processor.youtube import (
    TranscriptSegment,
    VideoExtraction,
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
        segments=(
            TranscriptSegment(0, 10, "first spoken sentence"),
            TranscriptSegment(65, 10, "second spoken sentence"),
        ),
    )
    chunks = transcript_chunks(video, target_words=100, overlap_words=0, interval_seconds=60)
    assert len(chunks) == 1
    assert "[00:00](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=0s)" in chunks[0].body
    assert "[01:05](https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=65s)" in chunks[0].body
