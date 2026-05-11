"""
Test /chat_edit: free-form Chinese prompts → LLM routes to tracks → Ableton updated
"""
import urllib.request, json, base64, time

PULSEFORMER = "http://localhost:8000"
BRIDGE      = "http://localhost:8002"


def post(url, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    resp = urllib.request.urlopen(req, timeout=180)
    return json.loads(resp.read())


def get(url):
    resp = urllib.request.urlopen(url, timeout=30)
    return json.loads(resp.read())


def show_result(label, r):
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"  status: {r['status']}")
    if r["status"] == "no_edits":
        print(f"  LLM said no changes needed")
        print(f"  raw: {r.get('llm_response','')[:100]}")
        return
    for item in r.get("results", []):
        s = item["status"]
        track = item["track"]
        if s == "ok":
            ops_str = ", ".join(o["op"] for o in item["ops_applied"])
            print(f"  OK {track:15s}  [{ops_str}]  "
                  f"notes: {item['notes_before']} -> {item['notes_after']}")
        else:
            print(f"  ✗ {track:15s}  {s}")


# ── Step 1: Generate + Import ─────────────────────────────────────────────────
print("Generating and importing stems...")
gen = post(f"{PULSEFORMER}/generate/segment", {
    "bpm": 128, "key": "C_MINOR", "struct": "DROP",
    "tracks": ["DRUMS", "BASS", "CHORD", "MELODY"],
    "e_level": 7, "bars": 8, "temperature": 0.85, "top_p": 0.92,
    "return_base64": True,
})
imp = post(f"{BRIDGE}/import_stems", {
    "midi_base64": gen["midi_base64"],
    "view_mode": "arrange",
    "key": "C_MINOR",
})
print(f"Imported: BPM={imp['bpm']}")
for t in imp["injected"]:
    print(f"  TOMI-{t['track']:6s}  track={t['index']}  notes={t['notes']}")

# ── Step 2: Free-form Chinese prompts ─────────────────────────────────────────

test_prompts = [
    "让旋律更稀疏一些，去掉大概一半的音符",
    "鼓的时间轴加一点人性化的随机感，让它听起来不那么机械",
    "整体音量偏小，bass下移一个八度，melody的力度也调柔和一点",
    "把所有轨道的音符都量化到16分音符网格上",
    "melody反转，同时鼓的力度统一设成90",
]

for i, prompt in enumerate(test_prompts, 1):
    print(f"\n{'─'*55}")
    print(f"[{i}] 指令: {prompt}")
    t0 = time.time()
    r = post(f"{BRIDGE}/chat_edit", {"instruction": prompt, "seed": i})
    elapsed = time.time() - t0
    show_result(f"({elapsed:.1f}s)", r)

print(f"\n{'='*55}")
print("完成！请查看 Ableton Arrange view 中的变化。")
