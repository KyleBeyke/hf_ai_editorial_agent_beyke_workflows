"""Hugging Face AI Editorial Agent.

This package is intentionally small enough to study but complete enough to run:

- scout recent AI topics from public web/RSS/API sources;
- scrape the beykeworkflows.com AI archive for existing article titles/excerpts;
- score candidate topics while penalizing exact and partial duplicates;
- use model-assisted topic selection, research synthesis, review, and prompt-file-based generation;
- generate or fall back to a featured image;
- write raw hook events, research artifacts, and final editorial outputs.

The design favors deterministic control flow around model calls. The model drafts,
but Python code owns crawling, duplicate checks, validation, output writing, and
event logging.
"""

__version__ = "0.4.0"
