"""
End-to-end test: PulseFormer → Ableton Arrange view
Usage: python scripts/test_pulseformer_to_ableton.py
"""
import urllib.request, json, socket, base64, tempfile, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pretty_midi

API = "http://localhost:8000"
ABLETON_HOST, ABLETON_PORT = "localhost", 9877
TRACK_ORDER = ["DRUMS", "BASS", "CHORD", "MELODY"]


def rpc(cmd, params=None):
    s = socket.socket()
    s.settimeout(15)
    s.connect((ABLETON_HOST, ABLETON_PORT))
    s.sendall(json.dumps({"type": cmd, "params": params or {}}).encode())
    data = b""
    while True:
        try:
            chunk = s.recv(8192)
            if not chunk:
                break
            data += chunk
            try:
                res = json.loads(data)
                if res.get("status") == "error":
                    raise RuntimeError(res.get("message"))
                return res.get("result", {})
            except json.JSONDecodeError:
                continue
        except socket.timeout:
            break
    s.close()
    return {}


# ── 1. PulseFormer generate ───────────────────────────────────────────────────
print("=== Step 1: PulseFormer generate (128BPM, C_MINOR, DROP, 8bars) ===")
payload = json.dumps({
    "bpm": 128, "key": "C_MINOR", "struct": "DROP",
    "tracks": ["DRUMS", "BASS", "CHORD", "MELODY"],
    "e_level": 6, "bars": 8, "temperature": 0.85, "top_p": 0.92,
    "return_base64": True,
}).encode()
req = urllib.request.Request(
    f"{API}/generate/segment", data=payload,
    headers={"Content-Type": "application/json"}, method="POST",
)
resp = urllib.request.urlopen(req, timeout=120)
midi_b64 = json.loads(resp.read())["midi_base64"]
raw = base64.b64decode(midi_b64)
print(f"  OK  MIDI size: {len(raw)} bytes")

# ── 2. Parse MIDI ─────────────────────────────────────────────────────────────
print("=== Step 2: Parse MIDI ===")
with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
    tmp.write(raw)
    tmp_path = tmp.name
pm = pretty_midi.PrettyMIDI(tmp_path)
os.unlink(tmp_path)

tempo_times, tempos = pm.get_tempo_changes()
bpm = float(tempos[0]) if len(tempos) > 0 else 128.0
beats_per_sec = bpm / 60.0
print(f"  BPM from MIDI tempo map: {bpm:.1f}")

name_to_track = {t: t for t in TRACK_ORDER}
ch_to_track = {9: "DRUMS", 0: "BASS", 1: "CHORD", 2: "MELODY"}
track_notes = {t: [] for t in TRACK_ORDER}

for inst in pm.instruments:
    if inst.is_drum:
        tname = "DRUMS"
    elif inst.name.upper() in name_to_track:
        tname = name_to_track[inst.name.upper()]
    elif inst.program in ch_to_track:
        tname = ch_to_track[inst.program]
    else:
        tname = None
    if not tname:
        print(f"  (skip)  {inst.name!r} prog={inst.program}")
        continue
    for n in inst.notes:
        track_notes[tname].append({
            "pitch":      n.pitch,
            "start_time": round(n.start * beats_per_sec, 4),
            "duration":   round((n.end - n.start) * beats_per_sec, 4),
            "velocity":   n.velocity,
        })
    print(f"  {tname:6s}  ({inst.name!r} prog={inst.program}): {len(inst.notes)} notes")

all_notes = [n for notes in track_notes.values() for n in notes]
clip_length = max(n["start_time"] + n["duration"] for n in all_notes) if all_notes else 32.0
print(f"  Clip length: {clip_length:.2f} beats  ({clip_length / 4:.1f} bars)")

# ── 3. Ableton: set BPM ───────────────────────────────────────────────────────
print("=== Step 3: Ableton set BPM ===")
rpc("set_tempo", {"tempo": round(bpm)})
print(f"  OK  BPM = {round(bpm)}")

# ── 4. Inject into Arrange view ───────────────────────────────────────────────
print("=== Step 4: Inject stems into Arrange view ===")
injected = []
for name in TRACK_ORDER:
    notes = track_notes[name]
    if not notes:
        print(f"  {name}: (empty, skip)")
        continue
    res = rpc("create_midi_track", {"index": -1})
    t_idx = res.get("index", -1)
    rpc("set_track_name", {"track_index": t_idx, "name": f"TOMI-{name}"})
    rpc("create_arrangement_clip", {"track_index": t_idx, "position": 0.0, "length": clip_length})
    for i in range(0, len(notes), 500):
        rpc("add_notes_to_arrangement_clip",
            {"track_index": t_idx, "clip_index": 0, "notes": notes[i:i+500]})
    injected.append({"track": name, "notes": len(notes), "index": t_idx})
    print(f"  OK  TOMI-{name:6s}  → track {t_idx}  ({len(notes)} notes)")

print()
print("=== Done! Open Ableton Arrange view ===")
print(json.dumps({"bpm": round(bpm), "clip_beats": round(clip_length, 2), "injected": injected}, indent=2))
