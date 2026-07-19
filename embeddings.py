"""Локальные эмбеддинги: llama-server --embedding, OpenAI-совместимый /v1/embeddings.

Модель по умолчанию — nomic-embed-text-v1.5 (уже была скачана локально
для LM Studio, мультиязычная, 768 измерений). Сервер поднимается
отдельно: `powershell -File start-embed-server.ps1` (см. README) —
эмбеддинги не привязаны к жизни агента, чтобы отсутствие сервера не
роняло базовый функционал (fulltext-кэш и т.п.), только RAG-часть.

nomic-embed-text обучен с префиксами задачи — без них хуже ранжирует:
документы получают "search_document: ", запросы — "search_query: ".
"""
import json
import os
import urllib.error
import urllib.request

import numpy as np

EMBED_URL = os.environ.get("RESEARCH_EMBED_URL", "http://127.0.0.1:8099/v1/embeddings")
DIM = 768


def _embed_batch(texts, prefix):
    body = json.dumps({"input": [prefix + t for t in texts]}).encode()
    req = urllib.request.Request(EMBED_URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"эмбеддинг-сервер недоступен на {EMBED_URL} ({e}). "
            "Запусти: powershell -File start-embed-server.ps1"
        ) from e
    by_index = sorted(resp["data"], key=lambda d: d["index"])
    return np.array([d["embedding"] for d in by_index], dtype=np.float32)


def embed_documents(texts):
    if not texts:
        return np.zeros((0, DIM), dtype=np.float32)
    return _embed_batch(texts, "search_document: ")


def embed_query(text):
    return _embed_batch([text], "search_query: ")[0]
