from __future__ import annotations

from pathlib import Path

from shiny import App, Inputs, Outputs, Session, reactive, render, ui

from learn_processor.pipeline import ProcessingOptions, process_files
from learn_processor.youtube import javascript_runtime_status

APP_DIR = Path(__file__).resolve().parent


app_ui = ui.page_fluid(
    ui.tags.head(
        ui.tags.title("Learn Library Builder"),
        ui.tags.style(
            """
            body { background: #f4f6f8; }
            .app-shell { max-width: 1180px; margin: 0 auto; padding: 2rem 1rem 3rem; }
            .hero { margin-bottom: 1.25rem; }
            .hero h1 { font-weight: 700; letter-spacing: -0.03em; }
            .control-card { height: 100%; border: 0; box-shadow: 0 4px 20px rgba(24,39,58,.08); }
            .control-card .card-header { background: white; font-weight: 650; padding-top: 1rem; }
            .muted { color: #5f6b78; }
            .status-box { white-space: pre-wrap; background: #101820; color: #d7e2ea;
                          border-radius: .5rem; padding: 1rem; min-height: 8rem; }
            .result-card { border-left: 4px solid #198754; }
            .run-progress { display: none; align-items: center; gap: .75rem; margin-top: 1rem; }
            .run-progress.is-active { display: flex; }
            """
        ),
        ui.tags.script(
            """
            document.addEventListener("DOMContentLoaded", () => {
                const button = document.getElementById("process");
                const indicator = document.getElementById("run-progress");
                if (!button || !indicator) return;

                button.addEventListener("click", () => {
                    indicator.classList.add("is-active");
                    button.setAttribute("aria-busy", "true");
                    window.setTimeout(() => { button.disabled = true; }, 0);
                });

                $(document).on("shiny:idle", () => {
                    indicator.classList.remove("is-active");
                    button.disabled = false;
                    button.removeAttribute("aria-busy");
                });
            });
            """
        ),
    ),
    ui.div(
        ui.div(
            ui.h1("Learn Library Builder"),
            ui.p(
                "Turn searchable books and YouTube speech into structured, timestamped Markdown.",
                class_="lead muted",
            ),
            class_="hero",
        ),
        ui.layout_columns(
            ui.card(
                ui.card_header("1. Upload sources"),
                ui.input_file(
                    "uploads",
                    "Choose EPUB, searchable PDF, or YouTube link list",
                    accept=[".epub", ".pdf", ".txt"],
                    multiple=True,
                ),
                ui.p(
                    "Text files may contain one or more youtube.com or youtu.be links. "
                    "Blank lines and lines beginning with # are ignored.",
                    class_="muted",
                ),
                ui.p(javascript_runtime_status(), class_="small muted"),
                ui.tags.hr(),
                ui.h6("Supported processing"),
                ui.tags.ul(
                    ui.tags.li("EPUB: reading order and headings are retained."),
                    ui.tags.li(
                        "PDF: searchable text, table of contents, and page references are retained."
                    ),
                    ui.tags.li(
                        "YouTube: captions or local speech-to-text with links back to exact times."
                    ),
                ),
                class_="control-card",
            ),
            ui.card(
                ui.card_header("2. Specify output"),
                ui.input_text(
                    "output_dir",
                    "Output folder",
                    value=str(APP_DIR / "processed_library"),
                ),
                ui.layout_columns(
                    ui.input_numeric(
                        "chunk_words", "Target words per chunk", 1200, min=250, max=5000
                    ),
                    ui.input_numeric("overlap_words", "Overlap words", 120, min=0, max=1000),
                    col_widths=(6, 6),
                ),
                ui.input_numeric(
                    "timestamp_interval",
                    "YouTube timestamp interval (seconds)",
                    60,
                    min=15,
                    max=600,
                ),
                ui.input_text("languages", "Caption language priority", value="en,en-US,en-GB"),
                ui.input_checkbox(
                    "whisper_fallback",
                    "Use local Whisper when YouTube captions are unavailable",
                    True,
                ),
                ui.layout_columns(
                    ui.input_select(
                        "whisper_model",
                        "Local Whisper model",
                        {
                            "tiny": "Tiny (fastest)",
                            "base": "Base",
                            "small": "Small (recommended)",
                            "medium": "Medium (most accurate)",
                        },
                        selected="small",
                    ),
                    ui.input_select(
                        "whisper_device",
                        "Transcription device",
                        {"cpu": "CPU (easiest setup)", "cuda": "NVIDIA GPU (CUDA configured)"},
                        selected="cpu",
                    ),
                    col_widths=(6, 6),
                ),
                ui.p(
                    "Existing output is never overwritten. "
                    "A numbered version folder is created instead.",
                    class_="muted",
                ),
                ui.input_action_button(
                    "process", "Build Markdown library", class_="btn-primary w-100"
                ),
                ui.div(
                    ui.div(
                        class_="spinner-border spinner-border-sm text-primary",
                        role="status",
                        **{"aria-hidden": "true"},
                    ),
                    ui.span(
                        "Processing is in progress. Keep this window open until the run finishes."
                    ),
                    id="run-progress",
                    class_="run-progress alert alert-info",
                    role="status",
                    **{"aria-live": "polite"},
                ),
                class_="control-card",
            ),
            col_widths=(6, 6),
        ),
        ui.card(
            ui.card_header("Run status"),
            ui.output_text_verbatim("status", placeholder=False),
            ui.output_ui("results"),
            class_="mt-4",
        ),
        class_="app-shell",
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    status_value = reactive.value("Ready. Add source files and choose an output folder.")
    result_value = reactive.value([])

    @reactive.effect
    @reactive.event(input.process)
    def _run_processing() -> None:
        uploads = input.uploads()
        if not uploads:
            status_value.set("No files selected. Upload at least one EPUB, PDF, or TXT file.")
            result_value.set([])
            return

        try:
            chunk_words = int(input.chunk_words())
            overlap_words = int(input.overlap_words())
            if overlap_words >= chunk_words:
                raise ValueError("Overlap must be smaller than the target chunk size.")

            languages = tuple(item.strip() for item in input.languages().split(",") if item.strip())
            if not languages:
                raise ValueError("Enter at least one caption language code.")

            raw_output_dir = str(input.output_dir()).strip().strip('"')
            if not raw_output_dir:
                raise ValueError("Choose an output folder.")
            options = ProcessingOptions(
                output_dir=Path(raw_output_dir).expanduser(),
                chunk_words=chunk_words,
                overlap_words=overlap_words,
                timestamp_interval=int(input.timestamp_interval()),
                languages=languages,
                whisper_fallback=bool(input.whisper_fallback()),
                whisper_model=str(input.whisper_model()),
                whisper_device=str(input.whisper_device()),
            )
            paths = [(Path(item["datapath"]), item["name"]) for item in uploads]

            status_value.set(
                "Processing sources. Large books or local transcription can take several minutes."
            )
            with ui.Progress(min=0, max=len(paths)) as progress:
                progress.set(message="Building Markdown library", detail="Starting")

                def update(done: int, total: int, message: str) -> None:
                    progress.set(done, message="Building Markdown library", detail=message)
                    status_value.set(f"Processed {done} of {total} uploads\n{message}")

                results = process_files(paths, options, progress=update)

            result_value.set(results)
            failures = [item for item in results if not item.success]
            status_value.set(
                f"Finished with {len(results) - len(failures)} successful source(s) "
                f"and {len(failures)} failure(s).\nOutput: {options.output_dir.resolve()}"
            )
        except (
            Exception
        ) as exc:  # UI boundary: show a concise error instead of crashing the session.
            status_value.set(f"Processing stopped: {exc}")
            result_value.set([])

    @output
    @render.text
    def status() -> str:
        return status_value.get()

    @output
    @render.ui
    def results():
        items = result_value.get()
        if not items:
            return ui.div()
        cards = []
        for item in items:
            if item.success:
                cards.append(
                    ui.div(
                        ui.strong(item.label),
                        ui.div(f"{item.chunk_count} chunk(s), {item.word_count:,} words"),
                        ui.code(str(item.output_path)),
                        class_="alert alert-success result-card",
                    )
                )
            else:
                cards.append(
                    ui.div(ui.strong(item.label), ui.div(item.error), class_="alert alert-danger")
                )
        return ui.div(*cards)


app = App(app_ui, server)
