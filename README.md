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

## Windows quick start

### 1. Install Python once

Install a 64-bit version of Python 3.11 or newer from the [official Windows downloads page](https://www.python.org/downloads/windows/). Python 3.12 or 3.13 is recommended. During a traditional installer setup, enable the Python launcher or add Python to `PATH`.

### 2. Install Deno for complete YouTube support

YouTube captions can be retrieved without Deno. Reliable metadata and audio download for local Whisper fallback require Deno 2 or newer, as required by current versions of `yt-dlp`.

Open PowerShell and run:

```powershell
winget install DenoLand.Deno
```

Close and reopen any terminal windows after installation. Node 20 or newer is also supported and is detected automatically, but Deno is the recommended runtime.

### 3. Download the app

On the [Learn repository page](https://github.com/dwu388/Learn), select **Code**, then **Download ZIP**. Extract the ZIP into a normal folder such as `Documents\Learn`. Do not run the batch file from inside the ZIP preview.

If Git is already installed, cloning works too:

```powershell
git clone https://github.com/dwu388/Learn.git
cd Learn
```

### 4. Launch

Double-click `run_app.bat`.

On the first launch, the script:

1. Finds a compatible 64-bit Python installation.
2. Creates a private `.venv` environment inside the app folder.
3. Updates the Python installation tools.
4. Installs and verifies the app dependencies.
5. Starts the app on an available local port and opens it in the default browser.

The first setup can take several minutes. Later launches skip installation unless the environment is missing, outdated, or broken. Keep the batch window open while using the app.

## Process source material

1. Under **Upload sources**, select one or more `.epub`, searchable `.pdf`, or `.txt` files.
2. For YouTube, place one video link per line in a UTF-8 text file. Lines beginning with `#` are ignored.
3. Under **Specify output**, enter the destination folder. The default is `processed_library` inside the app folder.
4. Keep the default 1,200-word chunks and 120-word overlap unless a different retrieval system requires other limits.
5. For YouTube, leave the timestamp interval at 60 seconds for a useful balance between readability and precise review links.
6. Leave **CPU** selected for the simplest Whisper setup. Select NVIDIA GPU only after CUDA 12 and cuDNN 9 are correctly configured.
7. Select **Build Markdown library** and keep the browser and batch window open until the run finishes.

The first Whisper fallback downloads the selected speech-to-text model and therefore takes longer. Captioned videos do not need this model.

## Stop and restart

- To stop the app, return to the batch window and press `Ctrl+C`.
- To start it again, double-click `run_app.bat`.
- Closing only the browser tab does not stop the local server.

The app writes only to the output folder you specify. Existing source folders are never overwritten. Repeated processing creates `-v2`, `-v3`, and later versions, and `catalog.md` retains all completed sources.

## Troubleshooting

- **Python was not found:** install 64-bit Python 3.11 or newer, then reopen `run_app.bat`.
- **Dependency setup was interrupted:** double-click `setup_app.bat`, wait for a successful completion message, and run the app again.
- **The browser did not open:** use the local address printed in the batch window.
- **A PDF is rejected:** confirm that text can be selected and copied in a PDF reader. OCR-only scans are intentionally unsupported.
- **YouTube audio download fails:** run `deno --version`. It must report version 2 or newer. Then restart the app.
- **CUDA transcription fails:** switch the transcription device back to CPU. GPU mode requires a separately working CUDA 12 and cuDNN 9 installation.

## Developer verification

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest
```

Run the app from a terminal with:

```powershell
.venv\Scripts\python.exe -m shiny run --port 0 --launch-browser --no-dev-mode app.py
```
