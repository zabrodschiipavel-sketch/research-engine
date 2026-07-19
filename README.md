# research-engine

Исследовательский агент с двумя взаимозаменяемыми драйверами —
DeepSeek и Gemini (оба через нативный function calling): сам решает,
какие запросы слать в OpenAlex, CORE и Brave Search, читает найденные
источники и пишет итоговый отчёт по промпту.

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
[sources.py](sources.py) (`search_openalex`, `search_core`,
`get_fulltext`, `search_brave`) — сравнение моделей получается на
равных условиях. Пример прогона обеих моделей на одинаковых темах —
[comparisons/2026-07-19-deepseek-vs-gemini](comparisons/2026-07-19-deepseek-vs-gemini/SUMMARY.md).

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
