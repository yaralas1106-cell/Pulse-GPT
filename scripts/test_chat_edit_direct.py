# -*- coding: utf-8 -*-
"""
Test /chat_edit logic directly without HTTP server.
Simulates the endpoint using in-memory track state.
"""
import sys
sys.path.insert(0, "d:/BigData/PycharmProject/TOMI-GPT")

from agent.llm_ableton_editor import ask_llm_chat_edit, apply_ops

# Simulate the _track_state that the bridge holds after import_stems
_track_state = {
    "TOMI-DRUMS": {
        "notes": [],          # blank section (what user sees)
        "bpm": 128,
        "key": "C_MINOR",
        "is_drum": True,
        "track_index": 5,
        "clip_index": 0,
        "view_mode": "arrange",
    },
    "TOMI-BASS": {
        "notes": [{"pitch": 36, "start_time": 0.0, "duration": 2.0, "velocity": 90}],
        "bpm": 128,
        "key": "C_MINOR",
        "is_drum": False,
        "track_index": 6,
    },
}

instruction = "39-49小节出现完全空白 帮我加入鼓组的pattern完善"
print(f"Instruction: {instruction}")
print("Calling ask_llm_chat_edit...")

edits, raw = ask_llm_chat_edit(_track_state, instruction)
print(f"Raw LLM/rule response: {raw[:100]}")
print(f"Edits: {edits}")

if not edits:
    print("\nRESULT: no_edits — FAIL")
else:
    print("\nRESULT: edits detected — PASS")
    for edit in edits:
        tname = edit["track"]
        ops   = edit["ops"]
        state = _track_state.get(tname)
        if not state:
            print(f"  Track {tname} not in state — skip")
            continue
        notes_before = state["notes"]
        notes_after  = apply_ops(notes_before, ops, seed=1)
        print(f"  {tname}: {len(notes_before)} -> {len(notes_after)} notes")
        for op in ops:
            print(f"    op={op}")
        if notes_after:
            t_min = min(n["start_time"] for n in notes_after)
            t_max = max(n["start_time"] for n in notes_after)
            pitches = sorted(set(n["pitch"] for n in notes_after))
            print(f"    beat range: {t_min:.1f} - {t_max:.1f}  (expected 152-196 for bars 39-49)")
            print(f"    pitches: {pitches}")
