"""Running memory: per-day briefings, user prefs, Q&A log (JSON file)."""
import json
import os

from . import config


def _blank():
    return {"briefings": {}, "prefs": {}, "qa_log": []}


def load():
    try:
        with open(config.MEMORY_FILE) as f:
            mem = json.load(f)
        for k, v in _blank().items():
            mem.setdefault(k, v)
        return mem
    except (FileNotFoundError, json.JSONDecodeError):
        return _blank()


def save(mem):
    tmp = config.MEMORY_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mem, f, indent=2)
    os.replace(tmp, config.MEMORY_FILE)


def record_briefing(mem, date_str, summary):
    mem["briefings"][date_str] = summary
    mem["qa_log"] = mem["qa_log"][-200:]  # bound growth
    save(mem)


def record_qa(mem, question, answer):
    mem["qa_log"].append({"q": question, "a": answer})
    mem["qa_log"] = mem["qa_log"][-200:]
    save(mem)
