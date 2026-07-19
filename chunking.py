"""Чанкинг полных текстов: по абзацам, ~1.5к символов, offset-точно.

Если абзац сам крупнее MAX_SIZE — режем его по границам предложений.
Без overlap: границы по абзацам и так сохраняют смысловые единицы
лучше, чем fixed-size нарезка (для которой overlap обычно и нужен).
"""
import re

TARGET_SIZE = 1500
MAX_SIZE = 2200


def _paragraph_spans(text):
    spans = []
    start = 0
    for m in re.finditer(r"\n\s*\n+", text):
        end = m.start()
        if end > start:
            spans.append((start, end))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _split_long_span(text, start, end, max_size):
    out = []
    pos = start
    for m in re.finditer(r"[.!?]\s+", text[start:end]):
        boundary = start + m.end()
        if boundary - pos >= max_size:
            out.append((pos, boundary))
            pos = boundary
    if pos < end:
        out.append((pos, end))
    return out


def split_text(text, target=TARGET_SIZE, max_size=MAX_SIZE):
    if not text or not text.strip():
        return []
    pieces = []
    for s, e in _paragraph_spans(text):
        if e - s <= max_size:
            pieces.append((s, e))
        else:
            pieces.extend(_split_long_span(text, s, e, max_size))
    chunks = []
    cur_start = cur_end = None
    for s, e in pieces:
        if cur_start is None:
            cur_start, cur_end = s, e
        elif e - cur_start <= target:
            cur_end = e
        else:
            chunks.append((cur_start, cur_end))
            cur_start, cur_end = s, e
    if cur_start is not None:
        chunks.append((cur_start, cur_end))
    return [
        {"start": s, "end": e, "text": text[s:e].strip()}
        for s, e in chunks
        if text[s:e].strip()
    ]
