# -*- coding: utf-8 -*-
"""
Populate data/bridge_state.json from a multi-track MIDI file.
Run this after a bridge restart to restore LLM editing state without Ableton.
"""
import sys, json
from pathlib import Path
sys.path.insert(0, "d:/BigData/PycharmProject/TOMI-GPT")
import pretty_midi

MIDI_PATH  = Path("d:/BigData/PycharmProject/TOMI-GPT/outputs/v46_ultimate_house_FULL.mid")
STATE_FILE = Path("d:/BigData/PycharmProject/TOMI-GPT/data/bridge_state.json")
BPM        = 128
KEY        = "C_MINOR"
VIEW_MODE  = "arrange"

TRACK_MAP = {
    "DRUMS":  {"track_index": 5, "is_drum": True},
    "BASS":   {"track_index": 6, "is_drum": False},
    "CHORD":  {"track_index": 7, "is_drum": False},
    "MELODY": {"track_index": 8, "is_drum": False},
}

pm = pretty_midi.PrettyMIDI(str(MIDI_PATH))
tempos = pm.get_tempo_changes()
if len(tempos[1]) > 0:
    BPM = round(tempos[1][0])

beats_per_sec = BPM / 60.0

state = {}
for inst in pm.instruments:
    role = inst.name.strip().upper()
    if role not in TRACK_MAP:
        # fallback: try channel
        ch_map = {9: "DRUMS", 0: "MELODY", 1: "BASS", 2: "CHORD"}
        role = ch_map.get(inst.program % 16, None)
    if role not in TRACK_MAP:
        continue

    notes = []
    for n in inst.notes:
        notes.append({
            "pitch":      int(n.pitch),
            "start_time": round(n.start * beats_per_sec, 4),
            "duration":   round((n.end - n.start) * beats_per_sec, 4),
            "velocity":   int(n.velocity),
        })
    notes.sort(key=lambda x: x["start_time"])

    clip_length = max((n["start_time"] + n["duration"] for n in notes), default=32.0)
    tname = f"TOMI-{role}"
    state[tname] = {
        "notes":       notes,
        "track_index": TRACK_MAP[role]["track_index"],
        "clip_index":  0,
        "view_mode":   VIEW_MODE,
        "clip_length": round(clip_length, 2),
        "bpm":         BPM,
        "key":         KEY,
        "is_drum":     TRACK_MAP[role]["is_drum"],
    }
    print(f"  {tname}: {len(notes)} notes, clip_length={clip_length:.1f} beats")

STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
print(f"\nSaved {len(state)} tracks to {STATE_FILE}")
