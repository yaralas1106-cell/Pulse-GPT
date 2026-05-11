# -*- coding: utf-8 -*-
"""Test rule-based fill_drums detection."""
import sys
sys.path.insert(0, "d:/BigData/PycharmProject/TOMI-GPT")

from agent.llm_ableton_editor import _detect_fill_drums, apply_ops

track_states = {
    "TOMI-DRUMS": {"notes": [], "bpm": 128, "key": "C_MINOR", "is_drum": True},
    "TOMI-BASS":  {"notes": [], "bpm": 128, "key": "C_MINOR", "is_drum": False},
}

# Test 1: original Chinese instruction
instruction1 = "39-49小节出现完全空白 帮我加入鼓组的pattern完善"
r1 = _detect_fill_drums(instruction1, track_states)
print("Test 1:", r1)

# Test 2: English
instruction2 = "bars 5-8 are empty, add minimal drums"
r2 = _detect_fill_drums(instruction2, track_states)
print("Test 2:", r2)

# Test 3: unrelated — should be None
instruction3 = "make the melody quieter"
r3 = _detect_fill_drums(instruction3, track_states)
print("Test 3 (should be None):", r3)

# Test 4: apply ops from test 1
if r1:
    notes = apply_ops([], r1[0]["ops"], seed=0)
    t_min = min(n["start_time"] for n in notes)
    t_max = max(n["start_time"] for n in notes)
    print(f"Test 4: {len(notes)} notes, beats {t_min:.1f} - {t_max:.1f}  (expected 152-196)")
