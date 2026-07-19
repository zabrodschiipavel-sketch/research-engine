"""SQLite-корпус: память между запусками (Фаза 1 ROADMAP).

Один файл corpus.db рядом со скриптами (или путь в RESEARCH_CORPUS_PATH).
Дедуп works по DOI/core_id/URL, кэш полных текстов CORE, FTS5-индекс
для search_corpus. Пишут сюда sources.py (найденные работы, кэш
фултекстов) и trace.py (метаданные запусков) — оба независимо, разные
таблицы одного файла.
"""
import json
import os
import re
import sqlite3
import time

DB_PATH = os.environ.get(
    "RESEARCH_CORPUS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus.db"),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    doi TEXT,
    core_id INTEGER,
    url TEXT,
    title TEXT,
    year INTEGER,
    authors TEXT,
    venue TEXT,
    cited_by INTEGER,
    abstract TEXT,
    description TEXT,
    extra TEXT,
    first_seen_run TEXT,
    last_seen_run TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_works_doi ON works(doi);
CREATE INDEX IF NOT EXISTS idx_works_core_id ON works(core_id);
CREATE INDEX IF NOT EXISTS idx_works_url ON works(url);

CREATE TABLE IF NOT EXISTS fulltexts (
    core_id INTEGER PRIMARY KEY,
    work_id INTEGER,
    full_text TEXT NOT NULL,
    total_chars INTEGER NOT NULL,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    provider TEXT,
    model TEXT,
    prompt_file TEXT,
    started_at TEXT,
    finished_at TEXT,
    rounds INTEGER,
    usage_json TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS works_fts USING fts5(
    work_id UNINDEXED,
    title,
    abstract,
    description,
    fulltext,
    tokenize = 'unicode61'
);
"""


def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(_SCHEMA)
    return con


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize_doi(doi):
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi or None


def _find_work(con, doi=None, source=None, core_id=None, url=None):
    doi = _normalize_doi(doi)
    if doi:
        row = con.execute("SELECT id FROM works WHERE doi = ?", (doi,)).fetchone()
        if row:
            return row[0]
    if source == "core" and core_id is not None:
        row = con.execute(
            "SELECT id FROM works WHERE source = 'core' AND core_id = ?", (core_id,)
        ).fetchone()
        if row:
            return row[0]
    if url:
        row = con.execute("SELECT id FROM works WHERE url = ?", (url,)).fetchone()
        if row:
            return row[0]
    return None


def _reindex_fts(con, work_id):
    w = con.execute(
        "SELECT title, abstract, description FROM works WHERE id = ?", (work_id,)
    ).fetchone()
    if not w:
        return
    title, abstract, description = w
    ft_row = con.execute(
        "SELECT full_text FROM fulltexts WHERE work_id = ?", (work_id,)
    ).fetchone()
    fulltext = ft_row[0] if ft_row else ""
    con.execute("DELETE FROM works_fts WHERE work_id = ?", (work_id,))
    con.execute(
        "INSERT INTO works_fts (work_id, title, abstract, description, fulltext) VALUES (?, ?, ?, ?, ?)",
        (work_id, title or "", abstract or "", description or "", fulltext or ""),
    )


def upsert_work(source, run_id=None, doi=None, core_id=None, url=None, title=None,
                 year=None, authors=None, venue=None, cited_by=None, abstract=None,
                 description=None, extra=None):
    con = _connect()
    try:
        wid = _find_work(con, doi=doi, source=source, core_id=core_id, url=url)
        now = _now()
        ndoi = _normalize_doi(doi)
        extra_json = json.dumps(extra, ensure_ascii=False) if extra else None
        if wid is None:
            cur = con.execute(
                """INSERT INTO works
                   (source, doi, core_id, url, title, year, authors, venue, cited_by,
                    abstract, description, extra, first_seen_run, last_seen_run,
                    created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source, ndoi, core_id, url, title, year, authors, venue, cited_by,
                 abstract, description, extra_json, run_id, run_id, now, now),
            )
            wid = cur.lastrowid
        else:
            # Свежие непустые значения побеждают, но не затирают старые пустотой.
            con.execute(
                """UPDATE works SET
                     doi = COALESCE(?, doi), core_id = COALESCE(?, core_id), url = COALESCE(?, url),
                     title = COALESCE(?, title), year = COALESCE(?, year), authors = COALESCE(?, authors),
                     venue = COALESCE(?, venue), cited_by = COALESCE(?, cited_by),
                     abstract = COALESCE(?, abstract), description = COALESCE(?, description),
                     last_seen_run = ?, updated_at = ?
                   WHERE id = ?""",
                (ndoi, core_id, url, title, year, authors, venue, cited_by, abstract,
                 description, run_id, now, wid),
            )
        _reindex_fts(con, wid)
        con.commit()
        return wid
    finally:
        con.close()


def ingest_openalex(results, run_id=None):
    return [
        upsert_work(
            source="openalex", run_id=run_id, doi=w.get("doi"), title=w.get("title"),
            year=w.get("year"), authors=w.get("authors"), venue=w.get("venue"),
            cited_by=w.get("cited_by"), abstract=w.get("abstract"),
            extra={"institution": w.get("institution")} if w.get("institution") else None,
        )
        for w in results
    ]


def ingest_core(results, run_id=None):
    return [
        upsert_work(
            source="core", run_id=run_id, doi=w.get("doi"), core_id=w.get("core_id"),
            title=w.get("title"), year=w.get("year"),
            extra={"fulltext_chars": w.get("fulltext_chars")},
        )
        for w in results
    ]


def ingest_brave(results, run_id=None):
    return [
        upsert_work(
            source="brave", run_id=run_id, url=w.get("url"), title=w.get("title"),
            description=w.get("description"),
            extra={"age": w.get("age")} if w.get("age") else None,
        )
        for w in results
    ]


def get_cached_fulltext(core_id):
    con = _connect()
    try:
        row = con.execute(
            "SELECT full_text, total_chars FROM fulltexts WHERE core_id = ?", (int(core_id),)
        ).fetchone()
        return row
    finally:
        con.close()


def cache_fulltext(core_id, full_text):
    core_id = int(core_id)
    con = _connect()
    try:
        wid_row = con.execute(
            "SELECT id FROM works WHERE source = 'core' AND core_id = ?", (core_id,)
        ).fetchone()
        wid = wid_row[0] if wid_row else None
        con.execute(
            """INSERT INTO fulltexts (core_id, work_id, full_text, total_chars, fetched_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(core_id) DO UPDATE SET
                   full_text = excluded.full_text, total_chars = excluded.total_chars,
                   fetched_at = excluded.fetched_at, work_id = excluded.work_id""",
            (core_id, wid, full_text, len(full_text), _now()),
        )
        if wid:
            _reindex_fts(con, wid)
        con.commit()
    finally:
        con.close()


def search(query, limit=8):
    con = _connect()
    cols = "w.id, w.source, w.title, w.year, w.authors, w.venue, w.cited_by, w.doi, w.core_id, w.url, w.abstract"
    sql = (
        f"SELECT {cols} FROM works_fts JOIN works w ON w.id = works_fts.work_id "
        "WHERE works_fts MATCH ? ORDER BY bm25(works_fts) LIMIT ?"
    )
    n = min(int(limit or 8), 20)
    try:
        rows = con.execute(sql, (query, n)).fetchall()
    except sqlite3.OperationalError:
        # Невалидный синтаксис FTS5-запроса (кавычки/двоеточия и т.п.) - фразовый поиск как фолбэк.
        safe = '"' + query.replace('"', '""') + '"'
        try:
            rows = con.execute(sql, (safe, n)).fetchall()
        except sqlite3.OperationalError as e:
            con.close()
            return {"error": f"некорректный запрос: {e}"}
    con.close()
    return [
        {
            "work_id": r[0], "source": r[1], "title": r[2], "year": r[3],
            "authors": r[4], "venue": r[5], "cited_by": r[6], "doi": r[7],
            "core_id": r[8], "url": r[9], "abstract": (r[10] or "")[:350],
        }
        for r in rows
    ]


def record_run_start(run_id, provider, model, prompt_file, started_at):
    con = _connect()
    try:
        con.execute(
            "INSERT OR REPLACE INTO runs (run_id, provider, model, prompt_file, started_at) VALUES (?,?,?,?,?)",
            (run_id, provider, model, prompt_file, started_at),
        )
        con.commit()
    finally:
        con.close()


def record_run_finish(run_id, finished_at, rounds, usage):
    con = _connect()
    try:
        con.execute(
            "UPDATE runs SET finished_at = ?, rounds = ?, usage_json = ? WHERE run_id = ?",
            (finished_at, rounds, json.dumps(usage, ensure_ascii=False), run_id),
        )
        con.commit()
    finally:
        con.close()
