# Learn Library Builder

A local Shiny for Python app that converts source material into structured Markdown for later retrieval and analysis.

## Inputs

- Searchable PDF books. OCR-only PDFs are rejected with a clear message.
- EPUB books.
- UTF-8 text files containing YouTube video links.

## Output

Each book or video receives its own versioned folder containing:

- `index.md`, with source metadata and links to every chunk
- `manifest.json`, with machine-readable provenance and chunk records
- `chunks/chunk-###.md`, with bounded word counts and optional overlap
- `original/`, for an archived copy of an uploaded book when enabled

PDF chunks retain page comments and page ranges. EPUBs retain their reading order and headings. YouTube transcript chunks retain clickable timestamps that open the original video at the matching spoken passage. The root `catalog.md` indexes successful outputs.

The conversion itself does not use an LLM. YouTube captions are preferred. When captions are unavailable, the optional local fallback downloads audio with `yt-dlp` and transcribes it with `faster-whisper`. The selected Whisper model is downloaded on first use.

## Windows launch

1. Install 64-bit Python 3.11 or newer from Python.org and ensure the `py` launcher is available.
2. Double-click `run_app.bat`.
3. The first launch creates `.venv` and installs dependencies. It can take several minutes because local transcription support is included.
4. The app opens at <http://127.0.0.1:8000>.

The app writes only to the output folder you specify. Existing source folders are never overwritten; repeated processing creates `-v2`, `-v3`, and later versions.

## Developer verification

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pytest
```

Run the app from a terminal with:

```powershell
.venv\Scripts\python.exe -m shiny run --launch-browser app.py
```
