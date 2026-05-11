"""Test fill_drums_pattern via /chat_edit endpoint."""
import urllib.request, json

def post(url, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())

# Test 1: original user instruction
print("=== Test 1: 原始指令 ===")
r = post("http://localhost:8002/chat_edit", {
    "instruction": "39-49小节出现完全空白 帮我加入鼓组的pattern完善",
    "seed": 1,
})
print("status:", r["status"])
if r["status"] == "no_edits":
    print("no_edits — LLM raw:", r.get("llm_response", "")[:200])
for item in r.get("results", []):
    ops = [o["op"] for o in item.get("ops_applied", [])]
    print(f"  {item['track']:15s}  {item['status']:10s}  ops={ops}")
    if item["status"] == "ok":
        print(f"    notes: {item['notes_before']} -> {item['notes_after']}")

# Test 2: direct apply_ops test (bypass LLM)
print("\n=== Test 2: apply_ops direct test ===")
import sys; sys.path.insert(0, r"d:\BigData\PycharmProject\TOMI-GPT")
from agent.llm_ableton_editor import apply_ops

ops = [{"op": "fill_drums_pattern", "bar_start": 39, "bar_end": 49, "style": "four_on_floor"}]
notes_before = []  # empty — simulating blank section
notes_after = apply_ops(notes_before, ops, seed=0)
print(f"Generated {len(notes_after)} notes for bars 39-49")
if notes_after:
    pitches = set(n["pitch"] for n in notes_after)
    t_min = min(n["start_time"] for n in notes_after)
    t_max = max(n["start_time"] for n in notes_after)
    print(f"  pitches: {sorted(pitches)}  time: {t_min:.1f} - {t_max:.1f} beats")
    # bar 39 starts at beat (39-1)*4 = 152
    print(f"  expected beat range: 152 - 196  (bars 39-49)")
