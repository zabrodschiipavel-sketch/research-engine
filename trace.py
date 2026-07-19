"""Трейс запусков агента: runs/<run_id>/ с полным логом раундов.

Раньше всё найденное агентом за прогон терялось — оставался только
финальный отчёт. Трейс — сырьё для corpus.py (Фаза 1) и для отладки
промптов: как раунды, так и то, что реально вернули инструменты.
"""
import json
import os
import time

import corpus

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


class RunTrace:
    def __init__(self, provider, model, prompt_file):
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.run_id = f"{ts}-{provider}"
        self.dir = os.path.join(RUNS_DIR, self.run_id)
        os.makedirs(self.dir, exist_ok=True)
        self.meta = {
            "run_id": self.run_id,
            "provider": provider,
            "model": model,
            "prompt_file": prompt_file,
            "started_at": ts,
        }
        self._calls_f = open(os.path.join(self.dir, "tool_calls.jsonl"), "w", encoding="utf-8")
        corpus.record_run_start(self.run_id, provider, model, prompt_file, ts)

    def log_call(self, round_no, name, args, result):
        self._calls_f.write(json.dumps(
            {"round": round_no, "name": name, "args": args, "result": result},
            ensure_ascii=False,
        ) + "\n")
        self._calls_f.flush()

    def finish(self, report_text, usage, rounds):
        self._calls_f.close()
        finished_at = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self.meta["usage"] = usage
        self.meta["rounds"] = rounds
        self.meta["finished_at"] = finished_at
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)
        with open(os.path.join(self.dir, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(report_text)
        corpus.record_run_finish(self.run_id, finished_at, rounds, usage)
        self._try_embed_pending()
        return self.dir

    @staticmethod
    def _try_embed_pending():
        # Best-effort: чанкинг+эмбеддинг новых fulltexts (Фаза 2). Не должен
        # ронять уже завершённый прогон, если эмбеддинг-сервер не поднят.
        try:
            r = corpus.embed_pending_chunks()
        except Exception as e:  # noqa: BLE001
            print(f"[embed] пропущено: {e}")
            return
        if r.get("error"):
            print(f"[embed] {r['error']}")
        elif r["embedded_works"]:
            print(f"[embed] {r['embedded_works']} работ, {r['chunks']} чанков")
