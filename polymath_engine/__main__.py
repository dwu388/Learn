"""SQLite-backed, source-grounded cross-domain concept discovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .wiki import ZimWikipedia

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, source_path TEXT NOT NULL,
 text_hash TEXT NOT NULL, status TEXT NOT NULL, error TEXT,
 processed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS concepts (
 id TEXT PRIMARY KEY, article_id TEXT NOT NULL REFERENCES articles(id),
 title TEXT NOT NULL, domain TEXT NOT NULL, problem TEXT NOT NULL,
 mechanism TEXT NOT NULL, conditions TEXT NOT NULL, failure_modes TEXT NOT NULL,
 evidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bridges (
 id TEXT PRIMARY KEY, left_id TEXT NOT NULL REFERENCES concepts(id),
 right_id TEXT NOT NULL REFERENCES concepts(id), similarity REAL NOT NULL,
 shared_terms TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'candidate',
 UNIQUE(left_id,right_id)
);
"""

STOPWORDS = frozenset(
    "a an the and or of for to from with in on at by is are was were be been "
    "has have had as it this that which their its into between over under "
    "through about such using use can may".split()
)


def terms(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z][a-z0-9]{2,}", text.casefold())
        if word not in STOPWORDS
    }


def similarity(a: dict, b: dict) -> tuple[float, list[str]]:
    """Transparent structural-token overlap; not semantic or causal validation."""
    left = terms(" ".join([a["problem"], a["mechanism"], *a["conditions"]]))
    right = terms(" ".join([b["problem"], b["mechanism"], *b["conditions"]]))
    if not left or not right:
        return 0.0, []
    common = sorted(left & right)
    return len(common) / len(left | right), common


def evidence_is_present(quote: str, text: str) -> bool:
    normalize = lambda s: re.sub(r"\s+", " ", s).strip().casefold()
    return len(quote.strip()) >= 24 and normalize(quote) in normalize(text)


def validate_record(raw: dict, article_text: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Concept must be an object")
    scalar = ("title", "domain", "problem", "mechanism", "evidence")
    obj = {}
    for key in scalar:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing text field: {key}")
        obj[key] = value.strip()[:1200]
    for key in ("conditions", "failure_modes"):
        value = raw.get(key)
        if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
            raise ValueError(f"Expected list of strings: {key}")
        obj[key] = [x.strip()[:350] for x in value[:6] if x.strip()]
    if not evidence_is_present(obj["evidence"], article_text):
        raise ValueError("Evidence quote is not present verbatim in supplied article")
    return obj


def call_ollama(url: str, model: str, title: str, text: str, timeout: int) -> list[dict]:
    endpoint = url.rstrip("/") + "/api/chat"
    prompt = (
        "Extract up to two reusable causal/problem-solving mechanisms from this "
        "Wikipedia text. Reply using the given JSON schema. Evidence must be a "
        "verbatim contiguous quote of at least 24 characters from the text. "
        "Do not guess missing facts, and return [] if no mechanism is supported.\n"
        f"ARTICLE: {title}\nTEXT:\n{text[:11500]}"
    )
    schema = {
        "type": "object", "properties": {
            "concepts": {"type": "array", "maxItems": 2, "items": {
                "type": "object", "properties": {
                    "title": {"type": "string"}, "domain": {"type": "string"},
                    "problem": {"type": "string"}, "mechanism": {"type": "string"},
                    "conditions": {"type": "array", "items": {"type": "string"}},
                    "failure_modes": {"type": "array", "items": {"type": "string"}},
                    "evidence": {"type": "string"}
                }, "required": [
                    "title", "domain", "problem", "mechanism", "conditions",
                    "failure_modes", "evidence"
                ], "additionalProperties": False
            }}
        }, "required": ["concepts"], "additionalProperties": False
    }
    payload = json.dumps({
        "model": model, "stream": False, "format": schema,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 800},
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=payload, headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        answer = json.load(response)
    content = answer["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("concepts"), list):
        raise ValueError("Ollama returned invalid concepts envelope")
    return parsed["concepts"][:2]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(SCHEMA)
    return db


def process_article(db: sqlite3.Connection, article, model: str, url: str,
                    timeout: int, force: bool = False) -> dict:
    article_id = digest(article.source_id)
    text_hash = digest(article.text)
    existing = db.execute(
        "SELECT text_hash, status FROM articles WHERE id=?", (article_id,)
    ).fetchone()
    if existing == (text_hash, "complete") and not force:
        return {"title": article.title, "status": "skipped"}
    # Never overwrite successful prior records when an inference fails.
    try:
        records = [
            validate_record(obj, article.text)
            for obj in call_ollama(url, model, article.title, article.text, timeout)
        ]
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError) as exc:
        if existing and existing[1] == "complete":
            return {"title": article.title, "status": "error_retained", "error": str(exc)}
        with db:
            db.execute(
                """INSERT INTO articles VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                error=excluded.error, processed_at=excluded.processed_at""",
                (article_id, article.title, article.path, text_hash,
                 "error", str(exc), datetime.now(timezone.utc).isoformat())
            )
        return {"title": article.title, "status": "error", "error": str(exc)}
    with db:
        db.execute("DELETE FROM bridges WHERE left_id IN "
                   "(SELECT id FROM concepts WHERE article_id=?) OR right_id IN "
                   "(SELECT id FROM concepts WHERE article_id=?)", (article_id, article_id))
        db.execute("DELETE FROM concepts WHERE article_id=?", (article_id,))
        db.execute(
            """INSERT INTO articles VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET title=excluded.title,
            source_path=excluded.source_path, text_hash=excluded.text_hash,
            status=excluded.status, error=NULL,
            processed_at=excluded.processed_at""",
            (article_id, article.title, article.path, text_hash, "complete", None,
             datetime.now(timezone.utc).isoformat())
        )
        for index, obj in enumerate(records):
            concept_id = digest(f"{article_id}:{index}:{obj['title']}")
            db.execute(
                "INSERT INTO concepts VALUES (?,?,?,?,?,?,?,?,?)",
                (concept_id, article_id, obj["title"], obj["domain"], obj["problem"],
                 obj["mechanism"], json.dumps(obj["conditions"]),
                 json.dumps(obj["failure_modes"]), obj["evidence"])
            )
    return {"title": article.title, "status": "complete", "concepts": len(records)}


def match_bridges(db: sqlite3.Connection, min_score: float = 0.12) -> int:
    rows = db.execute(
        "SELECT id,domain,problem,mechanism,conditions FROM concepts ORDER BY id"
    ).fetchall()
    concepts = [
        {"id": r[0], "domain": r[1], "problem": r[2],
         "mechanism": r[3], "conditions": json.loads(r[4])} for r in rows
    ]
    count = 0
    with db:
        db.execute("DELETE FROM bridges")
        for i, a in enumerate(concepts):
            for b in concepts[i+1:]:
                if a["domain"].casefold().strip() == b["domain"].casefold().strip():
                    continue
                score, shared = similarity(a, b)
                if score < min_score or len(shared) < 2:
                    continue
                db.execute(
                    "INSERT INTO bridges(id,left_id,right_id,similarity,shared_terms,status) "
                    "VALUES(?,?,?,?,?,?)",
                    (digest(a["id"] + b["id"]), a["id"], b["id"],
                     score, json.dumps(shared), "candidate")
                )
                count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wikipedia -> Qwen -> Polymath SQLite")
    parser.add_argument("--zim", type=Path, required=True, help="Existing Wikipedia .zim")
    parser.add_argument("--db", type=Path, default=Path("polymath_state/polymath.sqlite"))
    parser.add_argument("--model", default="qwen3.5:2b-q4_K_M")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--titles-file", type=Path, help="One Wikipedia article title per line")
    parser.add_argument("--title", action="append", default=[], help="Repeat for seed titles")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--min-score", type=float, default=0.12)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.timeout < 1 or not 0 <= args.min_score <= 1:
        parser.error("limit/timeout must be positive and min-score within [0,1]")
    titles = list(args.title)
    if args.titles_file:
        titles.extend(
            x.strip() for x in args.titles_file.read_text(encoding="utf-8-sig").splitlines()
            if x.strip() and not x.lstrip().startswith("#")
        )
    titles = list(dict.fromkeys(titles))[:args.limit]
    if not titles:
        parser.error("Supply --title or --titles-file; no uncontrolled full-wiki scan.")
    try:
        wiki = ZimWikipedia(args.zim)
        with connect(args.db) as db:
            for title in titles:
                try:
                    article = wiki.get(title)
                    result = process_article(
                        db, article, args.model, args.ollama_url, args.timeout, args.force
                    )
                except (OSError, ValueError, KeyError, RuntimeError) as exc:
                    result = {"title": title, "status": "error", "error": str(exc)}
                print(json.dumps(result, ensure_ascii=False), flush=True)
            matches = match_bridges(db, args.min_score)
            print(json.dumps({"candidate_bridges": matches, "db": str(args.db)}))
    except (OSError, RuntimeError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
