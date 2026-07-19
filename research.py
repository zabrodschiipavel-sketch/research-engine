"""Исследовательский агент: DeepSeek (tool calls) + OpenAlex/CORE/Brave.

Использование:
  python research.py <prompt_file> <out_file>   — полный агент с внешними тулами
  python research.py ask "вопрос"                — ответ ТОЛЬКО по корпусу (Фаза 2), без внешних API

DeepSeek сам решает, какие запросы слать в источники (до MAX_ROUNDS раундов), затем пишет отчёт.

Инструменты — в sources.py (общие с research_gemini.py). Секреты и модель
см. README.md (RESEARCH_SECRETS_PATH / RESEARCH_MODEL).
"""
import json
import os
import sys
import urllib.error
import urllib.request

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


def deepseek(messages, allow_tools=True):
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 16000,
        "reasoning_effort": "high",
        "thinking": {"type": "enabled"},
    }
    if allow_tools:
        payload["tools"] = TOOLS
    body = json.dumps(payload).encode()
    req = urllib.request.Request(DEEPSEEK_URL, data=body, headers={
        "Authorization": f"Bearer {SECRETS['deepseek']}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def main(prompt_file, out_file):
    prompt = open(prompt_file, encoding="utf-8").read()
    messages = [{"role": "user", "content": CORPUS_HINT + "\n\n" + prompt}]
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    trace = RunTrace("deepseek", MODEL, prompt_file)
    for round_no in range(MAX_ROUNDS):
        last = round_no == MAX_ROUNDS - 1
        if last:
            messages.append({"role": "user", "content": "Поиск завершён. Напиши финальный отчёт по ВСЕМ уже собранным результатам, строго по формату из задания."})
        try:
            resp = deepseek(messages, allow_tools=not last)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            if globals()["MODEL"] != "deepseek-v4-flash":
                print(f"model {MODEL} failed ({e.code}: {detail}), fallback to deepseek-v4-flash")
                globals()["MODEL"] = "deepseek-v4-flash"
                resp = deepseek(messages, allow_tools=not last)
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
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(report)
            trace.finish(report, total_usage, round_no + 1)
            print(f"DONE rounds={round_no + 1} usage={total_usage}")
            return
        for tc in calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"  [{round_no}] {name}({json.dumps(args, ensure_ascii=False)[:110]})")
            result = call_tool(name, args, run_id=trace.run_id)
            trace.log_call(round_no, name, args, result)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })
    trace.finish("", total_usage, MAX_ROUNDS)
    print("MAX_ROUNDS exceeded - report not produced")
    sys.exit(1)


def ask(question, limit=8):
    """Фаза 2: ответ по накопленному корпусу, без похода во внешние API.
    Один вызов DeepSeek на готовых источниках (гибридный BM25+вектор поиск)."""
    hits = corpus.hybrid_search(question, limit=limit)
    if not hits:
        print("В корпусе пока пусто или ничего не нашлось по этому запросу — сначала накопи источники обычными прогонами.")
        return
    sources_block = ""
    for i, h in enumerate(hits, 1):
        ident = h.get("doi") or h.get("url") or f"work_id={h['work_id']}"
        passage = h.get("best_chunk_text") or h.get("abstract") or ""
        sources_block += f"[{i}] {h.get('title')} ({ident})\n{passage[:1200]}\n\n"
    prompt = (
        "Ответь на вопрос СТРОГО по источникам ниже. После каждого утверждения "
        "указывай номер источника в квадратных скобках, например [2]. Если "
        "источников недостаточно для полного ответа — прямо скажи об этом, "
        "не выдумывай.\n\n"
        f"Вопрос: {question}\n\nИсточники:\n{sources_block}"
    )
    resp = deepseek([{"role": "user", "content": prompt}], allow_tools=False)
    answer = resp["choices"][0]["message"].get("content") or ""
    print(answer)
    print("\n---\nИсточники:")
    for i, h in enumerate(hits, 1):
        ident = h.get("doi") or h.get("url") or ""
        print(f"[{i}] {h.get('title')} {ident}")


if __name__ == "__main__":
    if sys.argv[1] == "ask":
        ask(sys.argv[2])
    else:
        main(sys.argv[1], sys.argv[2])
