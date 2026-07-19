# research-engine

Исследовательский агент на DeepSeek (tool calls): сам решает, какие
запросы слать в OpenAlex, CORE и Brave Search, читает найденные
источники и пишет итоговый отчёт по промпту.

Выделен из [ggrs](https://github.com/zabrodschiipavel-sketch/ggrs)
(`tools/research_agent.py`) в самостоятельный инструмент — база для
дальнейших обвязок (RAG, граф знаний и т.п.).

## Использование

```
python research.py <prompt_file> <out_file>
```

`prompt_file` — текст задания для агента (что исследовать и в каком
формате вернуть отчёт). Результат пишется в `out_file`.

## Секреты

Скопируйте `secrets.example.json` в `secrets.json` (лежит рядом со
скриптом, в `.gitignore`) и заполните ключи:

- `deepseek` — DeepSeek API key
- `openalex` — OpenAlex API key
- `core` — CORE API key
- `brave` — Brave Search API key (Free tier: 1 rps)

Путь к секретам можно переопределить переменной окружения
`RESEARCH_SECRETS_PATH`.

Модель DeepSeek задаётся переменной окружения `RESEARCH_MODEL`
(по умолчанию `deepseek-v4-pro`; при ошибке запроса автоматически
падает на `deepseek-v4-flash`).

## Зависимости

Только стандартная библиотека Python 3 — устанавливать нечего.
