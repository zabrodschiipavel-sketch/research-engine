# research-engine

Исследовательский агент с двумя взаимозаменяемыми драйверами —
DeepSeek и Gemini (оба через нативный function calling): сам решает,
какие запросы слать в OpenAlex, CORE, Brave Search и в свой же
локальный корпус (`corpus.db`), читает найденные источники и пишет
итоговый отчёт по промпту. Каждый прогон обогащает корпус — второй
запрос по той же теме находит источники локально и мгновенно, без
похода во внешние API (см. Фазу 1 в [ROADMAP.md](ROADMAP.md)).

Выделен из [ggrs](https://github.com/zabrodschiipavel-sketch/ggrs)
(`tools/research_agent.py`) в самостоятельный инструмент — база для
дальнейших обвязок (RAG, граф знаний и т.п., см. [ROADMAP.md](ROADMAP.md)).

## Использование

```
python research.py <prompt_file> <out_file>          # DeepSeek
python research_gemini.py <prompt_file> <out_file>    # Gemini
```

`prompt_file` — текст задания для агента (что исследовать и в каком
формате вернуть отчёт). Результат пишется в `out_file`.

Оба драйвера используют один и тот же набор инструментов из
[sources.py](sources.py) (`search_corpus`, `search_openalex`,
`search_core`, `get_fulltext`, `search_brave`) — сравнение моделей
получается на равных условиях. Пример прогона обеих моделей на
одинаковых темах —
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
  Локально, в `.gitignore` — не для коммита, для отладки и как сырьё
  для будущего чанкинга/эмбеддингов (Фаза 2).

И `runs/`, и `corpus.db` — чисто локальное состояние, ничего из этого
не публикуется. Подробности и сквозная проверка (два разных драйвера,
один и тот же корпус) — Фаза 1 в [ROADMAP.md](ROADMAP.md).

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

Только стандартная библиотека Python 3 — устанавливать нечего.
