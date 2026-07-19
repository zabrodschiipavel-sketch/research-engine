"""Исследовательский агент: DeepSeek (tool calls) + OpenAlex/CORE/Brave.

Использование:
  python research.py <prompt_file> <out_file>   — полный агент с внешними тулами
  python research.py ask "вопрос"                — ответ ТОЛЬКО по корпусу (Фаза 2), без внешних API
  python research.py deep <prompt_file> <out_file> — режим "глубокое исследование":
      тема разбивается на подтемы, каждая исследуется параллельно, затем
      синтезируется единый отчёт (см. deep_research() ниже)

DeepSeek сам решает, какие запросы слать в источники (до MAX_ROUNDS раундов), затем пишет отчёт.

Инструменты — в sources.py (общие с research_gemini.py). Секреты и модель
см. README.md (RESEARCH_SECRETS_PATH / RESEARCH_MODEL).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

import corpus
from sources import CORPUS_HINT, SECRETS, TOOL_SPECS, call_tool
from trace import RunTrace

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows-консоль по умолчанию не UTF-8

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
MAX_ROUNDS = 16

TOOLS = [{"type": "function", "function": spec} for spec in TOOL_SPECS]

# deepseek-v4-pro в thinking-режиме: tools поддержаны с V3.2;
# reasoning_content возвращается в message и ДОЛЖЕН уходить обратно в API
# при tool-цепочках — мы пересылаем message целиком, требование соблюдено.
MODEL = os.environ.get("RESEARCH_MODEL", "deepseek-v4-pro")


def deepseek(messages, allow_tools=True, tools=None, tool_choice=None, model=None, thinking=True):
    payload = {
        "model": model or MODEL,
        "messages": messages,
        "max_tokens": 16000,
        "reasoning_effort": "high",
    }
    # Просто не послать "thinking" - НЕ значит выключить его: у v4-семейства
    # thinking по умолчанию включён, нужен явный {"type": "disabled"} (см.
    # api-docs.deepseek.com/guides/thinking_mode - проверено вживую: без
    # этого forced tool_choice падает 400 "Thinking mode does not support
    # this tool_choice" даже при отсутствии ключа thinking в запросе).
    payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
    if allow_tools:
        payload["tools"] = tools if tools is not None else TOOLS
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
    body = json.dumps(payload).encode()
    req = urllib.request.Request(DEEPSEEK_URL, data=body, headers={
        "Authorization": f"Bearer {SECRETS['deepseek']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def run_agent_loop(prompt, trace, log_prefix=""):
    """Общий агентский цикл (раунды tool-calling до MAX_ROUNDS или пока модель
    не перестанет звать инструменты) — вынесен из main(), чтобы его переиспользовал
    и обычный прогон, и параллельные под-исследования в deep_research().

    Модель фолбэка (pro -> flash при HTTPError) хранится в ЛОКАЛЬНОЙ переменной,
    не в глобальной MODEL, как было раньше — иначе при параллельных вызовах из
    deep_research() один упавший поток тихо переключал бы модель всем остальным
    потокам разом. Возвращает (report_text, usage, rounds); report_text == ""
    при исчерпании MAX_ROUNDS без финального ответа."""
    model = MODEL
    messages = [{"role": "user", "content": CORPUS_HINT + "\n\n" + prompt}]
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    for round_no in range(MAX_ROUNDS):
        last = round_no == MAX_ROUNDS - 1
        if last:
            messages.append({"role": "user", "content": "Поиск завершён. Напиши финальный отчёт по ВСЕМ уже собранным результатам, строго по формату из задания."})
        try:
            resp = deepseek(messages, allow_tools=not last, model=model)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            if model != "deepseek-v4-flash":
                print(f"{log_prefix}model {model} failed ({e.code}: {detail}), fallback to deepseek-v4-flash")
                model = "deepseek-v4-flash"
                resp = deepseek(messages, allow_tools=not last, model=model)
            else:
                raise
        u = resp.get("usage", {})
        total_usage["prompt_tokens"] += u.get("prompt_tokens", 0)
        total_usage["completion_tokens"] += u.get("completion_tokens", 0)
        msg = resp["choices"][0]["message"]
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            report = msg.get("content") or ""
            trace.finish(report, total_usage, round_no + 1)
            return report, total_usage, round_no + 1
        for tc in calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"{log_prefix}[{round_no}] {name}({json.dumps(args, ensure_ascii=False)[:110]})")
            result = call_tool(name, args, run_id=trace.run_id)
            trace.log_call(round_no, name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })
    trace.finish("", total_usage, MAX_ROUNDS)
    return "", total_usage, MAX_ROUNDS


def main(prompt_file, out_file):
    prompt = open(prompt_file, encoding="utf-8").read()
    trace = RunTrace("deepseek", MODEL, prompt_file)
    report, usage, rounds = run_agent_loop(prompt, trace)
    if not report:
        print("MAX_ROUNDS exceeded - report not produced")
        sys.exit(1)
    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    print(f"DONE rounds={rounds} usage={usage}")


# --- Фаза 5 (внеплановая): "глубокое исследование" — декомпозиция на подтемы,
# параллельный fan-out, синтез. Инструмент декомпозиции живёт здесь, не в
# sources.py — это не тул для самого research-агента (тот его никогда не
# вызывает), а разовый служебный вызов оркестратора.

N_SUBTOPICS = int(os.environ.get("RESEARCH_DEEP_SUBTOPICS", "5"))
MAX_WORKERS = int(os.environ.get("RESEARCH_DEEP_WORKERS", "5"))

DECOMPOSE_TOOL = {
    "type": "function",
    "function": {
        "name": "emit_subtopics",
        "description": "Разбить тему исследования на несколько независимых подтем для параллельного поиска.",
        "parameters": {
            "type": "object",
            "properties": {
                "subtopics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Короткое название подтемы (для логов и имени файла)"},
                            "prompt": {"type": "string", "description": "Полная, самодостаточная формулировка задания для этой подтемы — как отдельный промпт для research-агента, с той же структурой требований к отчёту, что и в исходном задании"},
                        },
                        "required": ["title", "prompt"],
                    },
                },
            },
            "required": ["subtopics"],
        },
    },
}


def decompose_topic(prompt, n_subtopics=N_SUBTOPICS):
    """Разбивает тему на n_subtopics подтем через форсированный tool call —
    надёжнее, чем парсить JSON из свободного текста ответа."""
    messages = [{"role": "user", "content": (
        f"Разбей следующее исследовательское задание на {n_subtopics} независимых "
        f"подтем для параллельного поиска. Каждая подтема — самодостаточный "
        f"промпт для отдельного research-агента (та же структура требований к "
        f"отчёту, что и в исходном задании, но по своему узкому аспекту). Подтемы "
        f"должны вместе покрывать тему, минимально пересекаясь друг с другом.\n\n"
        f"Задание:\n{prompt}"
    )}]
    # thinking=False обязателен: DeepSeek отвечает 400 "Thinking mode does not
    # support this tool_choice" на форсированный вызов конкретного тула в
    # режиме рассуждений (проверено вживую, не по докам).
    resp = deepseek(
        messages, allow_tools=True, tools=[DECOMPOSE_TOOL], thinking=False,
        tool_choice={"type": "function", "function": {"name": "emit_subtopics"}},
    )
    call = resp["choices"][0]["message"]["tool_calls"][0]
    args = json.loads(call["function"]["arguments"])
    return args["subtopics"]


def synthesize_deep_report(original_prompt, subtopic_results):
    """Финальный синтез: сшивает под-отчёты по подтемам в один связный отчёт.
    Не конкатенация — отдельный DeepSeek-вызов, который видит все под-отчёты
    сразу и должен убрать дублирование, выстроить общую структуру и сохранить
    конкретные факты/ссылки на источники."""
    parts = [f"=== Подтема: {r['title']} ===\n{r['report']}\n" for r in subtopic_results]
    combined = "\n".join(parts)
    prompt = (
        "Ниже — независимо собранные материалы по нескольким подтемам одного "
        "общего исследовательского задания. Напиши ЕДИНЫЙ связный отчёт по "
        "исходному заданию, объединяя находки из всех подтем: убери дублирование "
        "между подтемами, выстрой общую структуру (не просто подряд подтемы), "
        "сохрани все конкретные факты и ссылки на источники из под-отчётов.\n\n"
        f"Исходное задание:\n{original_prompt}\n\nМатериалы по подтемам:\n{combined}"
    )
    resp = deepseek([{"role": "user", "content": prompt}], allow_tools=False)
    u = resp.get("usage", {})
    text = resp["choices"][0]["message"].get("content") or ""
    return text, {"prompt_tokens": u.get("prompt_tokens", 0), "completion_tokens": u.get("completion_tokens", 0)}


def deep_research(prompt_file, out_file, n_subtopics=N_SUBTOPICS, max_workers=MAX_WORKERS):
    """Режим "глубокое исследование": декомпозиция на подтемы -> параллельный
    fan-out (каждая подтема — независимый run_agent_loop со своим RunTrace) ->
    синтез единого отчёта. Под-отчёты сохраняются рядом с итоговым файлом
    в <out_file>.subtopics/ — для прозрачности, не только финальный текст.

    Частичный отказ переживается: если часть подтем упала, отчёт синтезируется
    из тех, что удались, а провалы просто печатаются. Останавливаемся полностью
    только если не удалась ни одна."""
    t0 = time.monotonic()
    prompt = open(prompt_file, encoding="utf-8").read()
    print(f"[deep] раскладываю тему на подтемы...")
    subtopics = decompose_topic(prompt, n_subtopics=n_subtopics)
    print(f"[deep] {len(subtopics)} подтем:")
    for s in subtopics:
        print(f"  - {s['title']}")

    def worker(i, sub):
        trace = RunTrace("deepseek", MODEL, f"{prompt_file}#{sub['title']}")
        prefix = f"  [{i}:{sub['title'][:20]}] "
        try:
            report, usage, rounds = run_agent_loop(sub["prompt"], trace, log_prefix=prefix)
            return {"title": sub["title"], "report": report, "usage": usage, "rounds": rounds, "run_id": trace.run_id, "error": None}
        except Exception as e:  # noqa: BLE001 — один упавший поток не должен рушить остальные
            return {"title": sub["title"], "report": "", "usage": {}, "rounds": 0, "run_id": trace.run_id, "error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(worker, i, s) for i, s in enumerate(subtopics)]
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            status = "OK" if not res["error"] and res["report"] else f"FAILED: {res['error'] or 'MAX_ROUNDS'}"
            print(f"[deep] подтема «{res['title']}» — {res['rounds']} раундов — {status}")

    ok_results = [r for r in results if not r["error"] and r["report"]]
    failed = [r for r in results if r not in ok_results]
    if not ok_results:
        print("[deep] ни одна подтема не дала отчёта — прерываю")
        sys.exit(1)

    subtopics_dir = out_file + ".subtopics"
    os.makedirs(subtopics_dir, exist_ok=True)
    for r in ok_results:
        safe_name = re.sub(r"[^\w\-]+", "_", r["title"]).strip("_")[:60] or "subtopic"
        with open(os.path.join(subtopics_dir, f"{safe_name}.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(r["report"])

    print(f"[deep] синтезирую финальный отчёт из {len(ok_results)} подтем...")
    final_report, synth_usage = synthesize_deep_report(prompt, ok_results)
    with open(out_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(final_report)

    total_usage = {
        "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) for r in ok_results) + synth_usage["prompt_tokens"],
        "completion_tokens": sum(r["usage"].get("completion_tokens", 0) for r in ok_results) + synth_usage["completion_tokens"],
    }
    elapsed = time.monotonic() - t0
    print(f"DONE subtopics_ok={len(ok_results)}/{len(subtopics)} failed={len(failed)} "
          f"usage={total_usage} elapsed={elapsed:.1f}s")


def synthesize_answer(question, limit=8):
    """Фаза 2/4: ответ по накопленному корпусу, без похода во внешние API.
    Один вызов DeepSeek на готовых источниках (гибридный BM25+вектор поиск).
    Возвращает {"answer", "sources"} или {"error"} — не печатает, чтобы
    одинаково годиться и CLI (ask), и MCP-серверу (Фаза 4)."""
    hits = corpus.hybrid_search(question, limit=limit)
    if not hits:
        return {"error": "В корпусе пока пусто или ничего не нашлось по этому запросу — сначала накопи источники обычными прогонами."}
    sources_block = ""
    src_list = []
    for i, h in enumerate(hits, 1):
        ident = h.get("doi") or h.get("url") or f"work_id={h['work_id']}"
        passage = h.get("best_chunk_text") or h.get("abstract") or ""
        sources_block += f"[{i}] {h.get('title')} ({ident})\n{passage[:1200]}\n\n"
        src_list.append({"n": i, "title": h.get("title"), "id": ident})
    prompt = (
        "Ответь на вопрос СТРОГО по источникам ниже. После каждого утверждения "
        "указывай номер источника в квадратных скобках, например [2]. Если "
        "источников недостаточно для полного ответа — прямо скажи об этом, "
        "не выдумывай.\n\n"
        f"Вопрос: {question}\n\nИсточники:\n{sources_block}"
    )
    resp = deepseek([{"role": "user", "content": prompt}], allow_tools=False)
    answer = resp["choices"][0]["message"].get("content") or ""
    return {"answer": answer, "sources": src_list}


def ask(question, limit=8):
    """CLI-обёртка: печатает результат synthesize_answer в stdout."""
    result = synthesize_answer(question, limit=limit)
    if "error" in result:
        print(result["error"])
        return
    print(result["answer"])
    print("\n---\nИсточники:")
    for s in result["sources"]:
        print(f"[{s['n']}] {s['title']} {s['id']}")


if __name__ == "__main__":
    if sys.argv[1] == "ask":
        ask(sys.argv[2])
    elif sys.argv[1] == "deep":
        deep_research(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1], sys.argv[2])
