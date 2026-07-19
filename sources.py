"""Общие инструменты исследовательского агента: OpenAlex, CORE, Brave.

Провайдеро-независимо: TOOL_SPECS описывает каждый инструмент как
{name, description, parameters} (JSON Schema) — драйверы (research.py,
research_gemini.py) оборачивают их в формат конкретного API.

Секреты берутся из secrets.json рядом с этим файлом (см. secrets.example.json)
или из пути в переменной окружения RESEARCH_SECRETS_PATH.
"""
import json
import os
import time
import urllib.parse
import urllib.request

import corpus

SECRETS_PATH = os.environ.get(
    "RESEARCH_SECRETS_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.json"),
)
SECRETS = json.load(open(SECRETS_PATH, encoding="utf-8"))

CORPUS_HINT = (
    "Перед внешними инструментами (search_openalex/search_core/search_brave) "
    "проверь search_corpus — нужные источники могут уже быть в локальной базе "
    "с прошлых запусков, это бесплатно и мгновенно."
)

TOOL_SPECS = [
    {
        "name": "search_corpus",
        "description": "Поиск по локальной базе уже найденных источников (гибрид: BM25 по названиям/абстрактам/полным текстам + векторный поиск по чанкам, если доступен эмбеддинг-сервер — иначе тихо деградирует до BM25). Бесплатно и мгновенно — стоит проверить здесь до похода во внешние API.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
                "limit": {"type": "integer", "description": "1-20, дефолт 8"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_openalex",
        "description": "Поиск научных работ в OpenAlex (250M+ работ). Возвращает топ работ по релевантности: название, год, авторы, площадка, цитирования, DOI, фрагмент абстракта.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковая строка (английский эффективнее)"},
                "from_year": {"type": "integer", "description": "Год с (например 2024)"},
                "per_page": {"type": "integer", "description": "Сколько работ вернуть (1-15, дефолт 8)"},
                "sort_by_citations": {"type": "boolean", "description": "true = сортировать по цитированиям, false/нет = по релевантности"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_core",
        "description": "Поиск в CORE (открытые полные тексты статей). Лучше всего работает точный запрос title:\"Точное название\". Возвращает работы с длиной доступного полного текста и core_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Запрос, например title:\"The Era of 1-bit LLMs\""},
                "limit": {"type": "integer", "description": "1-5, дефолт 3"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_fulltext",
        "description": "Получить кусок полного текста работы из CORE по core_id (30000 символов за вызов; для длинных статей вызывай несколько раз с разным offset).",
        "parameters": {
            "type": "object",
            "properties": {
                "core_id": {"type": "integer"},
                "offset": {"type": "integer", "description": "Смещение в символах, дефолт 0"},
            },
            "required": ["core_id"],
        },
    },
    {
        "name": "search_brave",
        "description": "Живой веб-поиск Brave: GitHub, блоги, Hacker News, форумы, новости, китайские сайты. Дополняет OpenAlex (статьи) и CORE (полные тексты). Бюджет ограничен — формулируй запросы точно.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос (можно site:github.com, можно по-китайски)"},
                "count": {"type": "integer", "description": "1-10, дефолт 6"},
                "freshness": {"type": "string", "description": "Опционально: pd/pw/pm/py (день/неделя/месяц/год)"},
            },
            "required": ["query"],
        },
    },
]

_last_brave = [0.0]


def search_brave(query, count=6, freshness=None):
    wait = 1.1 - (time.monotonic() - _last_brave[0])
    if wait > 0:
        time.sleep(wait)  # Free Tier: 1 rps
    params = {"q": query, "count": min(int(count or 6), 10)}
    if freshness:
        params["freshness"] = freshness
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "X-Subscription-Token": SECRETS["brave"],
        "Accept": "application/json",
        "User-Agent": "research-engine/0.1",
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    _last_brave[0] = time.monotonic()
    out = []
    for w in (data.get("web") or {}).get("results", []):
        out.append({
            "title": w.get("title"),
            "url": w.get("url"),
            "description": (w.get("description") or "")[:300],
            "age": w.get("age"),
        })
    return out


def core_get(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {SECRETS['core']}",
        "User-Agent": "research-engine/0.1 (mailto:zabrodschii.pavel@gmail.com)",
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def search_core(query, limit=3):
    params = urllib.parse.urlencode({"q": query, "limit": min(int(limit or 3), 5)})
    data = core_get(f"https://api.core.ac.uk/v3/search/works/?{params}")
    out = []
    for w in data.get("results", []):
        out.append({
            "core_id": w.get("id"),
            "title": w.get("title"),
            "year": w.get("yearPublished"),
            "doi": w.get("doi"),
            "fulltext_chars": len(w.get("fullText") or ""),
        })
    return out


def get_fulltext(core_id, offset=0):
    core_id = int(core_id)
    offset = int(offset)
    cached = corpus.get_cached_fulltext(core_id)
    if cached is not None:
        full_text, total_chars = cached
    else:
        data = core_get(f"https://api.core.ac.uk/v3/works/{core_id}")
        full_text = data.get("fullText") or ""
        if not full_text:
            return {"error": "полный текст недоступен для этой записи"}
        corpus.cache_fulltext(core_id, full_text)
        total_chars = len(full_text)
    chunk = full_text[offset:offset + 30000]
    return {"total_chars": total_chars, "offset": offset, "text": chunk, "cached": cached is not None}


def reconstruct_abstract(inv_idx, limit=350):
    if not inv_idx:
        return ""
    pos = {}
    for word, idxs in inv_idx.items():
        for i in idxs:
            pos[i] = word
    text = " ".join(pos[i] for i in sorted(pos))
    return text[:limit]


def search_openalex(query, from_year=None, per_page=8, sort_by_citations=False):
    params = {
        "search": query,
        "per-page": min(int(per_page or 8), 15),
        "api_key": SECRETS["openalex"],
        "select": "title,publication_year,authorships,primary_location,cited_by_count,doi,abstract_inverted_index",
    }
    filters = []
    if from_year:
        filters.append(f"from_publication_date:{from_year}-01-01")
    if filters:
        params["filter"] = ",".join(filters)
    if sort_by_citations:
        params["sort"] = "cited_by_count:desc"
    url = "https://api.openalex.org/works?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode())
    out = []
    for w in data.get("results", []):
        auth = ", ".join(a["author"]["display_name"] for a in (w.get("authorships") or [])[:4])
        inst = ""
        for a in (w.get("authorships") or [])[:1]:
            insts = a.get("institutions") or []
            if insts:
                inst = insts[0].get("display_name", "")
        venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
        out.append({
            "title": w.get("title"),
            "year": w.get("publication_year"),
            "authors": auth,
            "institution": inst,
            "venue": venue,
            "cited_by": w.get("cited_by_count"),
            "doi": w.get("doi"),
            "abstract": reconstruct_abstract(w.get("abstract_inverted_index")),
        })
    return out


def search_corpus(query, limit=8):
    return corpus.hybrid_search(query, limit=limit)


TOOL_FUNCTIONS = {
    "search_corpus": search_corpus,
    "search_openalex": search_openalex,
    "search_core": search_core,
    "get_fulltext": get_fulltext,
    "search_brave": search_brave,
}

_INGEST = {
    "search_openalex": corpus.ingest_openalex,
    "search_core": corpus.ingest_core,
    "search_brave": corpus.ingest_brave,
}


def call_tool(name, args, run_id=None):
    try:
        result = TOOL_FUNCTIONS[name](**args)
    except Exception as e:  # noqa: BLE001 — вернуть ошибку модели
        return {"error": str(e)}
    ingest = _INGEST.get(name)
    if ingest is not None and isinstance(result, list):
        ingest(result, run_id=run_id)
    return result
