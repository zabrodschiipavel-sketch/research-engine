import corpus
import importlib
import sqlite3


def _make_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_corpus.db"
    monkeypatch.setattr(corpus, "DB_PATH", str(db_path))
    return db_path


def _count_rows(db_path, table):
    con = sqlite3.connect(db_path)
    try:
        return con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def _get_work(db_path, work_id):
    con = sqlite3.connect(db_path)
    try:
        return con.execute("SELECT * FROM works WHERE id = ?", (work_id,)).fetchone()
    finally:
        con.close()


def test_upsert_work_new_and_update_same_doi(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    wid1 = corpus.upsert_work("test", doi="10.1234/abc", title="First")
    wid2 = corpus.upsert_work("test", doi="HTTPS://DOI.ORG/10.1234/ABC", title="Updated")
    assert wid1 == wid2
    assert _count_rows(str(tmp_path / "test_corpus.db"), "works") == 1
    con = sqlite3.connect(str(tmp_path / "test_corpus.db"))
    try:
        row = con.execute("SELECT title FROM works WHERE id = ?", (wid1,)).fetchone()
        assert row[0] == "Updated"
    finally:
        con.close()


def test_upsert_work_dedup_by_openalex_id(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    wid1 = corpus.upsert_work("test", openalex_id="W123", title="First")
    wid2 = corpus.upsert_work("test", openalex_id="W123", title="Second")
    assert wid1 == wid2
    assert _count_rows(str(tmp_path / "test_corpus.db"), "works") == 1


def test_upsert_work_dedup_by_core_id(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    wid1 = corpus.upsert_work("core", core_id=123, title="First")
    wid2 = corpus.upsert_work("core", core_id=123, title="Second")
    assert wid1 == wid2
    assert _count_rows(str(tmp_path / "test_corpus.db"), "works") == 1


def test_upsert_work_dedup_by_url(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    wid1 = corpus.upsert_work("test", url="https://example.com/paper", title="First")
    wid2 = corpus.upsert_work("test", url="https://example.com/paper", title="Second")
    assert wid1 == wid2
    assert _count_rows(str(tmp_path / "test_corpus.db"), "works") == 1


def test_upsert_work_keeps_non_null_fields(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, monkeypatch)
    wid = corpus.upsert_work("test", doi="10.1234/abc", title="Original Title", abstract="Abs")
    corpus.upsert_work("test", doi="10.1234/abc", title=None, abstract="New Abs")
    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute("SELECT title, abstract FROM works WHERE id = ?", (wid,)).fetchone()
        assert row[0] == "Original Title"
        assert row[1] == "New Abs"
    finally:
        con.close()


def test_search_returns_only_matching_and_truncates_abstract(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    corpus.upsert_work("test", doi="10.1/a", title="Alpha paper", abstract="UniqueTermHere " + "x" * 400)
    corpus.upsert_work("test", doi="10.1/b", title="Beta paper", abstract="Nothing special")
    results = corpus.search("UniqueTermHere")
    assert len(results) == 1
    assert results[0]["title"] == "Alpha paper"
    assert len(results[0]["abstract"]) == 350


def test_search_malformed_query_does_not_raise(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    corpus.upsert_work("test", doi="10.1/a", title="Some title", abstract="Some abstract")
    result = corpus.search('foo:bar"')
    assert "error" in result or isinstance(result, list)


def test_graph_cites_with_and_without_target_in_corpus(tmp_path, monkeypatch):
    _make_db(tmp_path, monkeypatch)
    wid1 = corpus.upsert_work("test", doi="10.1/source", openalex_id="WSOURCE", title="Source")
    corpus.add_edges("cites", "WSOURCE", ["WTARGET1"])
    edges = corpus.graph_cites("10.1/source")
    assert edges[0]["openalex_id"] == "WTARGET1"
    assert edges[0]["in_corpus"] is False

    corpus.upsert_work("test", openalex_id="WTARGET1", title="Target", doi="10.1/target")
    edges = corpus.graph_cites("10.1/source")
    assert edges[0]["in_corpus"] is True
    assert edges[0]["title"] == "Target"


def test_cache_fulltext_roundtrip_and_update(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, monkeypatch)
    corpus.upsert_work("core", core_id=42, title="Work")
    corpus.cache_fulltext(42, "First fulltext")
    text, chars = corpus.get_cached_fulltext(42)
    assert text == "First fulltext"
    assert chars == len("First fulltext")

    corpus.cache_fulltext(42, "Updated fulltext longer")
    text, chars = corpus.get_cached_fulltext(42)
    assert text == "Updated fulltext longer"
    assert chars == len("Updated fulltext longer")
    assert _count_rows(str(db_path), "fulltexts") == 1
