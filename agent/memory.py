"""
agent/memory.py
===============
Persistent user preference storage — one JSON file per session_id.
"""

import json
from pathlib import Path

MEMORY_DIR = Path(__file__).parent / "memory_store"
MEMORY_DIR.mkdir(exist_ok=True)


def load(session_id: str) -> dict:
    p = MEMORY_DIR / f"{session_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save(session_id: str, store: dict) -> None:
    p = MEMORY_DIR / f"{session_id}.json"
    p.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
