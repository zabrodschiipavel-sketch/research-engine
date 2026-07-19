"""Трейс запусков агента: runs/<run_id>/ с полным логом раундов.

Раньше всё найденное агентом за прогон терялось — оставался только
финальный отчёт. Трейс — сырьё для corpus.py (Фаза 1) и для отладки
промптов: как раунды, так и то, что реально вернули инструменты.
"""
import json
import os
import time

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

    def log_call(self, round_no, name, args, result):
        self._calls_f.write(json.dumps(
            {"round": round_no, "name": name, "args": args, "result": result},
            ensure_ascii=False,
        ) + "\n")
        self._calls_f.flush()

    def finish(self, report_text, usage, rounds):
        self._calls_f.close()
        self.meta["usage"] = usage
        self.meta["rounds"] = rounds
        self.meta["finished_at"] = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        with open(os.path.join(self.dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False, indent=2)
        with open(os.path.join(self.dir, "report.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(report_text)
        return self.dir
