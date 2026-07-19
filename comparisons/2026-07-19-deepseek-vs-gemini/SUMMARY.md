# DeepSeek vs Gemini: сравнение на двух исследованиях

Дата: 2026-07-19. Один и тот же набор инструментов (`sources.py`:
`search_openalex`, `search_core`, `get_fulltext`, `search_brave`) отдан
обеим моделям через их нативный function calling —
`research.py` (DeepSeek v4 Pro) и `research_gemini.py` (Gemini 3.5
Flash). Встроенный `google_search` не использовался (см. «Находка про
google_search» ниже) — сравнение изолирует качество модели-оркестратора
от доступности инструментов.

Темы — не синтетика, а реальные вопросы для [ROADMAP.md](../../ROADMAP.md)
проекта (фазы 2 и 3):

- **A** — [prompt_a_hybrid_retrieval.txt](prompt_a_hybrid_retrieval.txt): гибридный BM25+vector retrieval в SQLite
- **B** — [prompt_b_citation_graph.txt](prompt_b_citation_graph.txt): citation-graph retrieval и GraphRAG

## Числа

| | DeepSeek A | Gemini A | DeepSeek B | Gemini B |
|---|---|---|---|---|
| Раундов | 6 | 4 | 6 | 4 |
| Вызовов инструментов | 14 | 3 | 14 | 3 |
| search_openalex | 3 | 0 | 5 | 1 |
| search_core / get_fulltext | 0 / 1 | 0 / 0 | 1 / 0 | 0 / 0 |
| search_brave | 10 | 3 | 8 | 2 |
| input/prompt tokens | 41 816 | 10 069 | 38 049 | 10 708 |
| output tokens (+ thinking) | 3 259 | 1 614 + 3 368 | 3 320 | 1 277 + 1 894 |
| Цена по прайсу провайдера* | ≈ $0.021 | $0 (free tier); ≈$0.060 по paid-прайсу | ≈ $0.019 | $0 (free tier); ≈$0.045 по paid-прайсу |

\* DeepSeek-v4-pro: $0.435/1M input, $0.87/1M output (api-docs.deepseek.com,
2026-07-19). Gemini 3.5 Flash free tier — $0 (лимитированный rate limit,
данные "used to improve our products"); paid tier $1.50/1M input,
$9.00/1M output включая thinking-токены (ai.google.dev/gemini-api/docs/pricing).

**Наблюдение:** Gemini использовал в 4-5 раз меньше токенов на раунд, но
paid-цена за эквивалентный прогон вышла бы выше DeepSeek — почти весь
разрыв в output-прайсинге ($9 против $0.87 за 1M), а не в объёме.
Бесплатность Gemini здесь — следствие free tier, а не природной дешевизны
модели.

## Качество и стиль отчётов

Читал оба отчёта по каждой теме полностью — [deepseek_a](deepseek_a_hybrid_retrieval.txt) vs [gemini_a](gemini_a_hybrid_retrieval.txt), [deepseek_b](deepseek_b_citation_graph.txt) vs [gemini_b](gemini_b_citation_graph.txt).

- **Глубина.** DeepSeek заметно подробнее: конкретные цифры из найденных
  источников (например «18–49 мс p50 на 19K документов» из репозитория
  fidx), попытки дойти до полного текста (`get_fulltext`, хоть и с
  промахом — вызвал с `core_id: 0`, не сделав перед этим `search_core`,
  получил пустой результат и просто пошёл дальше). Gemini компактнее и
  местами суше, зато не теряет структуру — обе темы уложились в
  запрошенный формат (`##`-заголовки, без таблиц, источники в конце).
- **Какие инструменты реально трогали.** DeepSeek методично перебирал
  `search_brave` + `search_openalex`, один раз попытался `search_core`.
  Gemini почти всё делал через `search_brave` (топик A — вообще ни разу
  не тронул `search_openalex`/`search_core`) и один раз `search_openalex`
  на тему B. То есть Gemini больше опирался на общий веб-поиск и
  параметрическую память, чем на специализированные научные инструменты,
  которые ему были явно доступны.
- **Точность цитат — проверил выборочно через OpenAlex.** Взял по DOI
  из каждого отчёта: `10.1145/3596512` (Bruch et al., DeepSeek A),
  `10.1145/1571941.1572114` (Cormack RRF, Gemini A),
  `10.1017/rsm.2026.10079` (BibliZap, DeepSeek B, статья 2026 года!),
  `10.1145/3726302.3729920` (CG-RAG, Gemini B) — **все четыре реальные**,
  названия совпадают (у Gemini заголовок Cormack чуть перефразирован:
  «Individual Bootstrap Methods» вместо настоящего «Individual Rank
  Learning Methods» — DOI верный, формулировка неточная). Edge et al.
  GraphRAG (arXiv:2404.16130, цитируют оба) не резолвится через OpenAlex
  по DOI-паттерну arXiv, но это реальная и хорошо известная статья
  Microsoft Research — проблема в моём DOI-запросе, не в цитате.
  На этой выборке — ни одной выдуманной ссылки ни у одной модели, но
  выборка маленькая (4 DOI), это не доказательство отсутствия галлюцинаций
  вообще.
- **Формат.** Оба уложились в просимую структуру и объём. Gemini местами
  вставлял LaTeX-нотацию ($...$) для формул — не запрещено промптом, но
  не просилось явно.

## Находка про встроенный google_search

Родной grounding-инструмент Gemini (`{"type": "google_search"}`)
отвечает `429 too_many_requests` на этом ключе даже вне контекста —
`Grounding with Google Search` тарифицируется отдельно от обычной
генерации и, похоже, требует биллинг на проекте; чистого free-tier
квота под него нет (см. `ai.google.dev/gemini-api/docs/pricing`: для
Gemini 3 — оплата за каждый search-запрос). `research_gemini.py`
поэтому по умолчанию даёт Gemini тот же `search_brave`, что и DeepSeek
(`RESEARCH_GEMINI_SEARCH=google` — переключатель на будущее, если
включишь биллинг).

Также при параллельном запуске обеих Gemini-тем сразу словили `429` уже
на обычной генерации (не grounding) — free tier Gemini 3.5 Flash держит
всего несколько запросов в минуту суммарно по ключу. При последовательном
запуске всё прошло чисто.

## Вывод

На этой паре тем DeepSeek даёт заметно более насыщенный, инструментально
обоснованный отчёт ценой ~3-4x токенов и раундов и небольшой, но
ненулевой платы за запуск. Gemini компактнее, дешевле по объёму токенов,
но на практике почти не пользовался специализированными научными
инструментами (OpenAlex/CORE) при живых альтернативах под рукой,
предпочитая общий веб-поиск, и упирается в rate limit free-tier раньше,
чем DeepSeek — в бюджет. Для быстрых/дешёвых прогонов и при небольшом
трафике Gemini free tier — разумный дефолт; для дотошного
research-отчёта с добором полных текстов DeepSeek пока выглядит сильнее.
Двух тем мало для окончательного вывода — это ориентир, не бенчмарк.
