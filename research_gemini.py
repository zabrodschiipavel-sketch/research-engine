"""Исследовательский агент: Gemini (Interactions API, function calling) + OpenAlex/CORE/Brave.

Использование: python research_gemini.py <prompt_file> <out_file>
Gemini сам решает, какие запросы слать в источники (до MAX_ROUNDS раундов), затем пишет отчёт.

Инструменты — в sources.py (общие с research.py). Секреты и модель
см. README.md (RESEARCH_SECRETS_PATH / RESEARCH_GEMINI_MODEL).
"""
import json
import os
import sys
import urllib.error
import urllib.request

from sources import SECRETS, TOOL_SPECS, call_tool

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MAX_ROUNDS = 16
MODEL = os.environ.get("RESEARCH_GEMINI_MODEL", "gemini-3.5-flash")

# Встроенный google_search (grounding) на этом ключе отвечает 429
# too_many_requests — Grounding with Google Search тарифицируется отдельно
# и, похоже, требует биллинг на проекте, бесплатного квота под него нет.
# По умолчанию поэтому у Gemini тот же search_brave, что у DeepSeek —
# сравнение честное (один набор инструментов, разные модели).
# Включить встроенный поиск (если включишь биллинг): RESEARCH_GEMINI_SEARCH=google
_web_search = os.environ.get("RESEARCH_GEMINI_SEARCH", "brave")
_specs = TOOL_SPECS if _web_search != "google" else [s for s in TOOL_SPECS if s["name"] != "search_brave"]
TOOLS = [{"type": "function", "name": s["name"], "description": s["description"], "parameters": s["parameters"]} for s in _specs]
if _web_search == "google":
    TOOLS.insert(0, {"type": "google_search"})


def gemini(input_items, allow_tools=True):
    payload = {
        "model": MODEL,
        "input": input_items,
        "store": False,
    }
    if allow_tools:
        payload["tools"] = TOOLS
    body = json.dumps(payload).encode()
    req = urllib.request.Request(GEMINI_URL, data=body, headers={
        "x-goog-api-key": SECRETS["gemini"],
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


def _extract_text(steps):
    return "".join(
        part.get("text", "")
        for s in steps if s.get("type") == "model_output"
        for part in s.get("content") or []
        if part.get("type") == "text"
    )


def main(prompt_file, out_file):
    prompt = open(prompt_file, encoding="utf-8").read()
    history = [{"type": "user_input", "content": [{"type": "text", "text": prompt}]}]
    total_usage = {"total_input_tokens": 0, "total_output_tokens": 0, "total_thought_tokens": 0}
    for round_no in range(MAX_ROUNDS):
        last = round_no == MAX_ROUNDS - 1
        if last:
            history.append({"type": "user_input", "content": [{"type": "text", "text": "Поиск завершён. Напиши финальный отчёт по ВСЕМ уже собранным результатам, строго по формату из задания."}]})
        try:
            resp = gemini(history, allow_tools=not last)
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode()[:300]
            except Exception:  # noqa: BLE001
                pass
            print(f"HTTP {e.code}: {detail}")
            raise
        u = resp.get("usage", {})
        for k in total_usage:
            total_usage[k] += u.get(k, 0)
        steps = resp.get("steps") or []
        history.extend(steps)
        calls = [s for s in steps if s.get("type") == "function_call"]
        if resp.get("status") == "completed" or not calls:
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(_extract_text(steps))
            print(f"DONE rounds={round_no + 1} usage={total_usage}")
            return
        for c in calls:
            name = c["name"]
            args = c.get("arguments") or {}
            print(f"  [{round_no}] {name}({json.dumps(args, ensure_ascii=False)[:110]})")
            result = call_tool(name, args)
            history.append({
                "type": "function_result",
                "name": name,
                "call_id": c["id"],
                "result": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            })
    print("MAX_ROUNDS exceeded - report not produced")
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
