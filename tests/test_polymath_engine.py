import sqlite3
from pathlib import Path
from types import SimpleNamespace

from polymath_engine.__main__ import (
    connect, evidence_is_present, match_bridges, process_article,
    similarity, validate_record,
)


def record(domain):
    return {
        "title": "Regulation", "domain": domain,
        "problem": "stabilize changing demand",
        "mechanism": "negative feedback stabilizes response",
        "conditions": ["measured response"],
        "failure_modes": ["slow response"],
        "evidence": "Negative feedback stabilizes a system."
    }


def test_exact_source_evidence():
    assert evidence_is_present(
        "Negative feedback stabilizes a system.",
        "Before. Negative\n feedback stabilizes a system. After."
    )
    assert not evidence_is_present(
        "Invented supporting statement with no source.",
        "Negative feedback stabilizes a system."
    )


def test_rejects_fabricated_quote():
    try:
        validate_record(record("biology"), "Unrelated text that contains no supporting quote.")
    except ValueError as exc:
        assert "Evidence" in str(exc)
    else:
        raise AssertionError("Expected a rejected fabricated quote")


def test_structural_similarity():
    a = record("biology")
    b = record("engineering")
    score, shared = similarity(a, b)
    assert score > 0
    assert "feedback" in shared


def test_sqlite_cross_domain_only(tmp_path):
    with connect(tmp_path / "polymath.sqlite") as db:
        for i, domain in enumerate(["biology", "engineering", "biology"]):
            db.execute(
                "INSERT INTO articles VALUES (?,?,?,?,?,?,?)",
                (str(i), str(i), str(i), "hash", "complete", None, "now")
            )
            r = record(domain)
            db.execute(
                "INSERT INTO concepts VALUES (?,?,?,?,?,?,?,?,?)",
                (str(i), str(i), r["title"], domain, r["problem"],
                 r["mechanism"], '["measured response"]', "[]", r["evidence"])
            )
        assert match_bridges(db) == 2
        rows = db.execute("SELECT similarity,status FROM bridges").fetchall()
        assert len(rows) == 2
        assert all(row[1] == "candidate" for row in rows)


def test_resumable_without_network(tmp_path, monkeypatch):
    article = SimpleNamespace(
        title="Feedback", path="A/Feedback",
        text="Negative feedback stabilizes a system.",
        source_id="zim:sample.zim:A/Feedback"
    )
    monkeypatch.setattr(
        "polymath_engine.__main__.call_ollama",
        lambda *args: [record("engineering")]
    )
    with connect(tmp_path / "polymath.sqlite") as db:
        first = process_article(db, article, "model", "http://127.0.0.1", 1)
        assert first["status"] == "complete"
        assert first["concepts"] == 1
        second = process_article(db, article, "model", "http://127.0.0.1", 1)
        assert second["status"] == "skipped"
