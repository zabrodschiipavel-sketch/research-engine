"""Исследовательский агент: DeepSeek (tool calls) + OpenAlex/CORE/Brave.

Использование: python research.py <prompt_file> <out_file>
DeepSeek сам решает, какие запросы слать в источники (до MAX_ROUNDS раундов), затем пишет отчёт.

Инструменты — в sources.py (общие с research_gemini.py). Секреты и модель
см. README.md (RESEARCH_SECRETS_PATH / RESEARCH_MODEL).
"""
import json
import os
import sys
import urllib.error
import urllib.request

from sources import SECRETS, TOOL_SPECS, call_tool

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
    messages = [{"role": "user", "content": prompt}]
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
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
            with open(out_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(msg.get("content") or "")
            print(f"DONE rounds={round_no + 1} usage={total_usage}")
            return
        for tc in calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"  [{round_no}] {name}({json.dumps(args, ensure_ascii=False)[:110]})")
            result = call_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })
    print("MAX_ROUNDS exceeded - report not produced")
    sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
