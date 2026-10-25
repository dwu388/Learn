# Wikipedia Polymath — local MVP

This **opt-in** pipeline uses an **existing Wikipedia ZIM archive** and the
local Ollama model `qwen3.5:2b-q4_K_M`. It is intentionally independent of
the Shiny PDF/EPUB/YouTube processor and does not change its outputs.

## Install (Windows PowerShell)

From the Learn repository directory:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements-polymath.txt
ollama list
ollama serve
```

If Ollama is already running in the background, **do not run another**
`ollama serve`. Confirm the model appears in `ollama list` exactly as
`qwen3.5:2b-q4_K_M`. Install or rename only if your listing differs.

Find your existing `.zim` path, then in another PowerShell terminal:

```powershell
.\.venv\Scripts\python.exe -m polymath_engine --zim "J:\\Wikipedia\\wikipedia_en_all.zim" --titles-file polymath_engine\seeds.txt --limit 12
```

**Replace the example ZIM path** with your actual archive location.
For a bounded preliminary smoke test:

```powershell
.\.venv\Scripts\python.exe -m polymath_engine --zim "YOUR_EXISTING_ARCHIVE.zim" --title "Homeostasis" --title "Control theory" --limit 2
```

The model runs on localhost by default and receives only bounded article
text. It is never given permission to operate the filesystem or run commands.

## Behavior

- Reads articles straight from the ZIM with `libzim`; no extra Wikipedia
  download or Kiwix HTTP port required. Only explicitly requested seed titles
  are accessed. A missing entry is reported, not silently replaced.
- Sends at most the first 11,500 characters of each article to Ollama.
  The extraction is intentionally a **pilot**, not full-article coverage.
- Validates the returned JSON and checks that each supporting quote occurs
  in the source article. If any claim lacks direct evidence, the article
  is marked failed rather than admitting fabricated provenance.
- Saves article hashes, provenance pointers, concept cards, and ranked
  candidate bridges into `polymath_state/polymath.sqlite`.
- On rerun, skips successfully processed unchanged articles. Use
  `--force` to reprocess. Failed titles can be retried.
- Compares concept tokens between *different* model-assigned domains via
  transparent Jaccard overlap. These are **candidate analogies, not established
  causal equivalences or validated scientific discoveries**.
- Rebuilds the simple small-dataset bridge table each invocation. Do not
  use this O(n²) matcher on full Wikipedia; move to embeddings / an ANN index
  before scale-up.

## Inspection

Use Python's built-in SQLite interface or SQLite Browser to inspect:

```sql
SELECT a.title, c.domain, c.title, c.mechanism, c.evidence
FROM concepts c JOIN articles a ON c.article_id=a.id;

SELECT c1.title AS source, c2.title AS target,
       b.similarity, b.shared_terms, b.status
FROM bridges b
JOIN concepts c1 ON b.left_id=c1.id
JOIN concepts c2 ON b.right_id=c2.id
ORDER BY b.similarity DESC;
```

All matches need human or stronger-model review of both source contexts.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_polymath_engine.py
```

The tests use mock article records and mock inference so they do not require
a ZIM archive, Ollama, GPU, or internet connection.

## Limitations

The ZIM must be readable by `libzim`. Archive builds differ in entry titles;
missing titles are expected to be reported. The 2B model may emit unsupported
JSON or extract unsupported ideas: provenance checks reject missing *quotes*,
not incorrect interpretations of real quotes. The simple matcher cannot
detect deep analogies without shared vocabulary and should be replaced by a
semantic/structural retrieval system before large-scale autonomous discovery.
No scheduled background job is installed by this PR.
