# research-engine

Исследовательский агент с двумя взаимозаменяемыми драйверами —
DeepSeek и Gemini (оба через нативный function calling): сам решает,
какие запросы слать в OpenAlex, CORE, Brave Search и в свой же
локальный корпус (`corpus.db`), читает найденные источники и пишет
итоговый отчёт по промпту. Каждый прогон обогащает корпус — второй
запрос по той же теме находит источники локально и мгновенно, без
похода во внешние API (см. Фазу 1 в [ROADMAP.md](ROADMAP.md)).

Выделен из [ggrs](https://github.com/zabrodschiipavel-sketch/ggrs)
(`tools/research_agent.py`) в самостоятельный инструмент, дальше
дообвязан локальным RAG (гибридный BM25+вектор поиск) и графом
цитирований — см. [ROADMAP.md](ROADMAP.md).

## Использование

```
python research.py <prompt_file> <out_file>          # DeepSeek
python research_gemini.py <prompt_file> <out_file>    # Gemini
```

`prompt_file` — текст задания для агента (что исследовать и в каком
формате вернуть отчёт). Результат пишется в `out_file`.

```
python research.py ask "вопрос"
```

Ответ ТОЛЬКО по накопленному корпусу (гибридный BM25+вектор поиск,
один синтезирующий вызов DeepSeek с цитатами) — без единого похода во
внешние API. Секунды, почти бесплатно. Требует эмбеддинг-сервер для
полноценного качества (см. «RAG» ниже) — без него тихо деградирует до
чистого BM25.

Оба драйвера используют один и тот же набор инструментов из
[sources.py](sources.py) (`search_corpus`, `search_openalex`,
`search_core`, `get_fulltext`, `search_brave`, `graph_cites`,
`graph_cited_by`, `graph_related`) — сравнение моделей получается на
равных условиях. Пример прогона обеих моделей на одинаковых темах —
[comparisons/2026-07-19-deepseek-vs-gemini](comparisons/2026-07-19-deepseek-vs-gemini/SUMMARY.md).

## Память между запусками

- `corpus.py` — SQLite (`corpus.db` рядом со скриптом, путь
  переопределяется `RESEARCH_CORPUS_PATH`). Всё, что находят
  `search_openalex`/`search_core`/`search_brave`, автоматически
  оседает в таблице `works` (дедуп по DOI/core_id/URL); `get_fulltext`
  сначала проверяет кэш и только потом идёт в CORE API. FTS5-индекс
  (`bm25`) даёт инструмент агента `search_corpus` — модели явно
  подсказано (`CORPUS_HINT`) проверять его до похода во внешние API.
- `trace.py` — полный лог каждого прогона в `runs/<run_id>/`:
  `meta.json` (провайдер/модель/usage/раунды) и `tool_calls.jsonl`
  (каждый вызов инструмента с аргументами и полным результатом).
  Локально, в `.gitignore` — не для коммита, для отладки.

И `runs/`, и `corpus.db` — чисто локальное состояние, ничего из этого
не публикуется. Подробности и сквозная проверка (два разных драйвера,
один и тот же корпус) — Фаза 1 в [ROADMAP.md](ROADMAP.md).

## RAG (Фаза 2)

Локальные эмбеддинги — `nomic-embed-text-v1.5` через `llama-server
--embedding` (мультиязычно, 768 измерений; модель уже была скачана
локально для LM Studio, отдельно ставить не надо):

```
powershell -File start-embed-server.ps1    # поднимает :8099
```

После этого в конце каждого прогона `trace.py` best-effort чанкует и
эмбеддит новые полные тексты (`chunking.py` + `embeddings.py` →
`chunks` в `corpus.db`) — сервер не поднят, чанкинг просто пропускается
с предупреждением, прогон не падает. `search_corpus` и `research.py
ask` используют `corpus.hybrid_search` — RRF-слияние BM25 и косинуса,
с деградацией до чистого BM25 при недоступном сервере.

Путь к серверу — `RESEARCH_EMBED_URL` (дефолт
`http://127.0.0.1:8099/v1/embeddings`, OpenAI-совместимый формат).
Gemini embeddings API как альтернатива — не реализовано, локальный
путь оказался достаточным.

## Граф цитирований (Фаза 3)

Детерминированный, без LLM — построен на полях OpenAlex, которые и так
приходят бесплатно вместе с `search_openalex` (`referenced_works` и
`related_works`, последнее — готовая оценка похожести от самого
OpenAlex, без своей co-citation эвристики):

- `graph_cites(doi)` — что работа цитирует; локально, бесплатно.
- `graph_related(doi)` — похожие работы по OpenAlex; локально, бесплатно.
- `graph_cited_by(doi)` — кто цитирует работу; **живой** запрос к
  OpenAlex (`filter=cites:...`), обогащает корпус найденными работами.

Все три принимают DOI (он уже есть в любом результате
`search_openalex`/`search_corpus`) — агент цепляет их естественно, без
дополнительного маппинга ID. LLM-извлечение сущностей, GraphRAG и
поиск путей между работами — сознательно не реализованы, см. Фазу 3 в
[ROADMAP.md](ROADMAP.md).

## Секреты

Скопируйте `secrets.example.json` в `secrets.json` (лежит рядом со
скриптом, в `.gitignore`) и заполните ключи:

- `deepseek` — DeepSeek API key
- `openalex` — OpenAlex API key
- `core` — CORE API key
- `brave` — Brave Search API key (Free tier: 1 rps)
- `gemini` — Gemini Developer API key (ai.google.dev), нужен для `research_gemini.py`
- `vertex_express` — Vertex AI Express Mode key (пока нигде не используется, добавлен про запас)

Путь к секретам можно переопределить переменной окружения
`RESEARCH_SECRETS_PATH`.

Модель DeepSeek — переменная окружения `RESEARCH_MODEL`
(по умолчанию `deepseek-v4-pro`; при ошибке запроса автоматически
падает на `deepseek-v4-flash`).

Модель Gemini — `RESEARCH_GEMINI_MODEL` (по умолчанию `gemini-3.5-flash`).
Веб-поиск для Gemini по умолчанию идёт через тот же `search_brave`, что
и у DeepSeek: встроенный grounding-инструмент `google_search` на
бесплатном ключе отвечает `429` (тарифицируется отдельно, похоже,
нужен биллинг на проекте — см. `comparisons/.../SUMMARY.md`). Включить
его, если биллинг появится: `RESEARCH_GEMINI_SEARCH=google`.

Free tier Gemini держит немного запросов в минуту суммарно на ключ —
если гоняете DeepSeek- и Gemini-драйвер параллельно (или несколько тем
через Gemini одновременно), может словиться `429 too_many_requests`
даже без `google_search`; тогда просто повторить чуть позже.

## Зависимости

Стандартная библиотека Python 3 + `numpy` (brute-force косинус для
векторного поиска — единственное исключение из принципа «stdlib-only»,
осознанно допущенное в ROADMAP). Сам эмбеддинг-сервер (`llama-server`)
— отдельный бинарник, не Python-зависимость.
