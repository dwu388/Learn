"""Local source-to-Markdown processing for the Learn app."""

from .pipeline import ProcessingOptions, ProcessingResult, process_files

__all__ = ["ProcessingOptions", "ProcessingResult", "process_files"]
