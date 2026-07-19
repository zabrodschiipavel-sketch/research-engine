"""MCP-сервер поверх корпуса research-engine (Фаза 4 ROADMAP).

Протокол (JSON-RPC 2.0 по stdio) реализован вручную, без пакета `mcp` —
следуя принципу проекта "stdlib + SQLite" (см. ROADMAP.md, «Принципы»).
Покрыт минимальный набор методов, которые реально использует MCP-клиент:
initialize, notifications/initialized, tools/list, tools/call, ping.

Инструменты — только READ-поверхность корпуса, не полный набор
research-агента: search_corpus, ask_corpus, graph_cites, graph_related,
graph_cited_by, get_fulltext. search_openalex/search_core/search_brave
сюда сознательно не включены — это инструменты, которые РАСТЯТ корпус
(research.py/research_gemini.py), а не читают его; смешать роли значило
бы, что любой MCP-клиент может незаметно жечь Brave/CORE лимиты просто
листая библиотеку.

Запуск (обычно — из конфига MCP-клиента, не руками):
  python mcp_server.py
Читает JSON-RPC запросы построчно из stdin, пишет ответы построчно в
stdout. Диагностика — в stderr (stdout зарезервирован под протокол).
"""
import json
import sys

sys.stdin.reconfigure(encoding="utf-8")
sys.stdout.reconfigure(encoding="utf-8")

import corpus
import research
import sources

SERVER_NAME = "research-engine"
SERVER_VERSION = "0.1.0"
DEFAULT_PROTOCOL_VERSION = "2024-11-05"


def _reuse(name):
    spec = next(s for s in sources.TOOL_SPECS if s["name"] == name)
    return {"name": spec["name"], "description": spec["description"], "inputSchema": spec["parameters"]}


TOOLS = [
    _reuse("search_corpus"),
    {
        "name": "ask_corpus",
        "description": (
            "Синтезированный ответ по накопленному корпусу с цитатами [1][2] — "
            "один вызов DeepSeek поверх гибридного поиска (то же, что "
            "search_corpus), без похода во внешние API. Дороже и медленнее "
            "search_corpus (реальный вызов LLM с деньгами и задержкой) — бери "
            "его, когда нужен готовый связный текст с цитатами, а не сырые "
            "хиты для собственного анализа."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Вопрос"},
                "limit": {"type": "integer", "description": "Сколько источников подмешать, 1-20, дефолт 8"},
            },
            "required": ["question"],
        },
    },
    _reuse("graph_cites"),
    _reuse("graph_related"),
    _reuse("graph_cited_by"),
    _reuse("get_fulltext"),
]

DISPATCH = {
    "search_corpus": lambda **kw: sources.search_corpus(**kw),
    "ask_corpus": lambda **kw: research.synthesize_answer(**kw),
    "graph_cites": lambda **kw: sources.graph_cites(**kw),
    "graph_related": lambda **kw: sources.graph_related(**kw),
    "graph_cited_by": lambda **kw: sources.graph_cited_by(**kw),
    "get_fulltext": lambda **kw: sources.get_fulltext(**kw),
}


def _send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(id_, result):
    _send({"jsonrpc": "2.0", "id": id_, "result": result})


def _error(id_, code, message):
    _send({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


def _call_tool(name, arguments):
    fn = DISPATCH.get(name)
    if fn is None:
        return {"content": [{"type": "text", "text": f"Неизвестный инструмент: {name}"}], "isError": True}
    try:
        result = fn(**arguments)
    except Exception as e:  # noqa: BLE001 — ошибку инструмента отдаём клиенту, не роняем сервер
        return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    is_error = isinstance(result, dict) and "error" in result
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def handle(msg):
    method = msg.get("method")
    id_ = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        _result(id_, {
            "protocolVersion": params.get("protocolVersion") or DEFAULT_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method == "tools/list":
        _result(id_, {"tools": TOOLS})
    elif method == "tools/call":
        result = _call_tool(params.get("name"), params.get("arguments") or {})
        _result(id_, result)
    elif method == "ping":
        _result(id_, {})
    elif id_ is not None:
        _error(id_, -32601, f"Method not found: {method}")
    # notifications (id отсутствует) любого другого метода — молча игнорируем.


def main():
    print(f"[{SERVER_NAME}] MCP stdio server started, corpus={corpus.DB_PATH}", file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[{SERVER_NAME}] bad JSON: {e}", file=sys.stderr)
            continue
        try:
            handle(msg)
        except Exception as e:  # noqa: BLE001 — одно кривое сообщение не должно ронять весь сервер
            print(f"[{SERVER_NAME}] handler error: {type(e).__name__}: {e}", file=sys.stderr)
            if msg.get("id") is not None:
                _error(msg["id"], -32603, f"Internal error: {e}")


if __name__ == "__main__":
    main()
