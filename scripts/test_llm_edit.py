"""
End-to-end test:
  1. PulseFormer generate MIDI
  2. POST /import_stems  → inject into Ableton Arrange view + populate _track_state
  3. GET  /state         → confirm state saved
  4. POST /llm_edit      → LLM modifies TOMI-MELODY ("make it more sparse and quieter")
  5. POST /llm_edit      → LLM modifies TOMI-DRUMS  ("add swing, humanize timing")

Usage:  python scripts/test_llm_edit.py
"""

import urllib.request, json, base64, time

PULSEFORMER = "http://localhost:8000"
BRIDGE      = "http://localhost:8002"


def post(url, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    resp = urllib.request.urlopen(req, timeout=180)
    return json.loads(resp.read())


def get(url):
    resp = urllib.request.urlopen(url, timeout=30)
    return json.loads(resp.read())


# ── Step 1: Generate ──────────────────────────────────────────────────────────
print("=" * 60)
print("Step 1: PulseFormer generate  (128BPM, C_MINOR, DROP, 8 bars)")
t0 = time.time()
gen = post(f"{PULSEFORMER}/generate/segment", {
    "bpm": 128, "key": "C_MINOR", "struct": "DROP",
    "tracks": ["DRUMS", "BASS", "CHORD", "MELODY"],
    "e_level": 6, "bars": 8,
    "temperature": 0.85, "top_p": 0.92,
    "return_base64": True,
})
midi_b64 = gen["midi_base64"]
print(f"  OK  MIDI {len(base64.b64decode(midi_b64))} bytes  ({time.time()-t0:.1f}s)")

# ── Step 2: Import to Ableton ─────────────────────────────────────────────────
print("\nStep 2: POST /import_stems  → Ableton Arrange view")
t0 = time.time()
imp = post(f"{BRIDGE}/import_stems", {
    "midi_base64": midi_b64,
    "view_mode":   "arrange",
    "key":         "C_MINOR",
})
print(f"  OK  BPM={imp['bpm']}  view={imp['view_mode']}  ({time.time()-t0:.1f}s)")
for item in imp["injected"]:
    print(f"      TOMI-{item['track']:6s}  track={item['index']}  notes={item['notes']}")

# ── Step 3: Check state ───────────────────────────────────────────────────────
print("\nStep 3: GET /state")
state = get(f"{BRIDGE}/state")
for tname, info in state["tracks"].items():
    print(f"  {tname:15s}  notes={info['notes']}  track_idx={info['track_index']}")

# ── Step 4: LLM edit MELODY ───────────────────────────────────────────────────
print("\nStep 4: POST /llm_edit  — TOMI-MELODY")
instruction = "make the melody more sparse: remove roughly half the notes, and lower the velocities to feel softer and more intimate"
print(f"  instruction: {instruction}")
t0 = time.time()
edit1 = post(f"{BRIDGE}/llm_edit", {
    "track_name":  "TOMI-MELODY",
    "instruction": instruction,
    "seed": 42,
})
for r in edit1["results"]:
    print(f"  {r['track']:15s}  status={r['status']}")
    if r["status"] == "ok":
        print(f"    ops:          {json.dumps(r['ops_applied'])}")
        print(f"    notes:        {r['notes_before']} → {r['notes_after']}")
    elif r.get("llm_response"):
        print(f"    llm_raw: {r['llm_response'][:120]}")
print(f"  ({time.time()-t0:.1f}s)")

# ── Step 5: LLM edit DRUMS ────────────────────────────────────────────────────
print("\nStep 5: POST /llm_edit  — TOMI-DRUMS")
instruction2 = "add subtle swing feel: humanize the timing slightly and give a slight velocity variation to make it feel more human"
print(f"  instruction: {instruction2}")
t0 = time.time()
edit2 = post(f"{BRIDGE}/llm_edit", {
    "track_name":  "TOMI-DRUMS",
    "instruction": instruction2,
    "seed": 7,
})
for r in edit2["results"]:
    print(f"  {r['track']:15s}  status={r['status']}")
    if r["status"] == "ok":
        print(f"    ops:          {json.dumps(r['ops_applied'])}")
        print(f"    notes:        {r['notes_before']} → {r['notes_after']}")
print(f"  ({time.time()-t0:.1f}s)")

print("\n" + "=" * 60)
print("Done! Check Ableton Arrange view — clips should be updated.")
