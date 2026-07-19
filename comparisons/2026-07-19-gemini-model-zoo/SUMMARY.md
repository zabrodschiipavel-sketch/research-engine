# Зоопарк моделей Gemini на двух темах

Дата: 2026-07-19. Обе темы из
[../2026-07-19-deepseek-vs-gemini](../2026-07-19-deepseek-vs-gemini/):
**A** — [prompt_a_hybrid_retrieval.txt](../2026-07-19-deepseek-vs-gemini/prompt_a_hybrid_retrieval.txt)
(гибридный BM25+vector retrieval), **B** —
[prompt_b_citation_graph.txt](../2026-07-19-deepseek-vs-gemini/prompt_b_citation_graph.txt)
(citation-graph retrieval / GraphRAG). Прогонял `RESEARCH_GEMINI_MODEL=<id>
python research_gemini.py`, серийно, с паузой 15–20с между моделями.

## Результат по каждой модели

| Модель | Тема A | Тема B | Раундов | Инструменты | Токены (in / out / thought) |
|---|---|---|---|---|---|
| `gemini-3.5-flash` | OK | OK | 4 | 3× `search_brave` (A и B) | ~10 000 / ~1 500 / ~2 600 |
| `gemini-3.1-flash-lite` | OK | OK | 1 / 1 | **ни одного** оба раза | 941–965 / 970–1058 / 0 |
| `gemini-3-flash-preview` | OK | OK | 1 / 1 | **ни одного** оба раза | 941–965 / 1071–1248 / 748–917 |
| `gemini-3.1-pro-preview` | **429** | **429** | — | — | `limit: 0` на free tier (см. ниже) |
| `gemini-2.5-pro` | **429** | **429** | — | — | `limit: 0` на free tier |
| `gemini-2.5-flash` | **404** retired | **404** retired | — | — | — |
| `gemini-2.5-flash-lite` | **404** retired | **404** retired | — | — | — |
| `gemini-2.0-flash` | **500** | **500** | — | — | — |

Тема A целиком отработана раньше на 3.5-flash в первом сравнении, тема B
для неё — тоже из первого сравнения. Полные тексты:
[gemini-3.1-flash-lite.txt](gemini-3.1-flash-lite.txt) /
[gemini-3-flash-preview.txt](gemini-3-flash-preview.txt) (тема A),
[gemini-3.1-flash-lite_topicB.txt](gemini-3.1-flash-lite_topicB.txt) /
[gemini-3-flash-preview_topicB.txt](gemini-3-flash-preview_topicB.txt) (тема B).
Логи: `_run_log.txt`, `_run_log2.txt` (тема A), `_run_log_b.txt` (тема B).

## Что подтвердилось на второй теме

Вторая тема прогонялась после того, как в `research_gemini.py` починили
обрезку текста ошибки (было 300 символов, стало парсинг JSON целиком) —
это дало точную причину вместо догадок:

1. **У Pro-тира буквально нулевая бесплатная квота — не догадка, а факт
   из ответа API.** Тело ошибки на обеих темах:
   `Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 0, model: gemini-3.1-pro`
   и то же самое для `gemini-2.5-pro` и метрики `..._input_token_count`.
   `limit: 0` — это не «попробуй позже», а «этому ключу Pro вообще не
   положен». API вежливо предлагает «Please retry in 7s» / «in 46s», но
   это generic-текст рейт-лимитера; при лимите 0 повторные попытки
   бессмысленны, поэтому больше не ретраил.
2. **404 на `gemini-2.5-flash`/`-flash-lite` и 500 на `gemini-2.0-flash`
   не зависят от темы** — идентичный текст ошибки на A и на B.
   Ожидаемо: это про доступность модели, не про содержание запроса.
3. **`3.1-flash-lite` и `3-flash-preview` ни разу не вызвали ни один
   инструмент ни на одной из двух тем** — не случайность конкретного
   промпта, а стабильное поведение этих моделей: они отвечают из
   параметрической памяти за один раунд, даже когда `search_openalex` /
   `search_core` / `search_brave` им доступны наравне с `gemini-3.5-flash`.

## Новое: поймана галлюцинированная ссылка

В `gemini-3.1-flash-lite_topicB.txt` среди источников:

> *«Citation-based retrieval in science» (Paper)… DOI: 10.1002/asi.24230
> (например, работы E. Garfield по тематике Cocitation).*

Проверил DOI через OpenAlex: **он реальный, но статья совсем о другом** —
«Modeling the online health information seeking process: Information
channel selection among university students» (Sbaffi & Zhao, 2019) —
про то, как студенты ищут информацию о здоровье в интернете, никакого
отношения к цитированию, Гарфилду или co-citation. Модель, судя по
всему, взяла DOI-подобную строку из памяти и приклеила к теме, которую
никогда не проверяла инструментом (`rounds=1`, ни одного tool call).
Это ровно тот сценарий, ради которого в `research-engine` вообще есть
`search_openalex`/`search_core` — и ровно то, что случается, когда
модель их не вызывает. В прошлом сравнении (DeepSeek/3.5-flash, оба
реально ходили в инструменты) на выборке 4 DOI фабрикаций не нашлось;
здесь — с первой же попытки у модели, которая инструменты игнорирует.

## Вывод

Картина не изменилась от темы к теме — то есть она про модели, а не про
конкретный промпт. На бесплатном ключе сегодня реально годится для
research-агента только `gemini-3.5-flash`: единственная модель, которая
и доступна, и по своей инициативе пользуется инструментами вместо того,
чтобы гадать по памяти. `3.1-flash-lite` и `3-flash-preview` дешевле и
быстрее, но теперь на двух темах и с одной пойманной галлюцинированной
ссылкой — это не «более дешёвый вариант того же самого», а другой,
менее надёжный режим работы. Pro-модели и `2.0-flash` на этом ключе не
подключить в принципе (нулевая квота / несовместимость с Interactions
API), не только сегодня — это уже подтверждённый факт API, а не рейт-лимит,
который стоит перепроверять.
