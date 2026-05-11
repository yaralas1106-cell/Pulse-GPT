"""
PulseFormer API — 客户端示例
用法: python api/client_example.py [--host 127.0.0.1] [--port 8000]
"""

import argparse
import base64
import json
import sys
import requests

parser = argparse.ArgumentParser()
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()
BASE = f"http://{args.host}:{args.port}"


def check(r, label=""):
    if r.status_code not in (200, 201):
        print(f"[FAIL] {label}: HTTP {r.status_code}\n{r.text}")
        sys.exit(1)
    return r


# ── 1. health ─────────────────────────────────────────────────────────────────
r = check(requests.get(f"{BASE}/health"), "health")
print("[OK] health:", r.json())

# ── 2. model info ─────────────────────────────────────────────────────────────
r = check(requests.get(f"{BASE}/model/info"), "model/info")
print("[OK] model info:", r.json())

# ── 3. 单段生成 (binary MIDI) ─────────────────────────────────────────────────
print("\n[*] 单段生成 DROP E=7 128BPM ...")
payload = {
    "bpm": 128,
    "key": "A_MINOR",
    "struct": "DROP",
    "tracks": ["DRUMS", "BASS", "CHORD", "MELODY"],
    "e_level": 7,
    "bars": 16,
    "max_new_tokens": 600,
    "temperature": 0.85,
    "top_p": 0.92,
}
r = check(requests.post(f"{BASE}/generate/segment", json=payload), "generate/segment")
out = "api/output_segment.mid"
with open(out, "wb") as f:
    f.write(r.content)
print(f"[OK] 保存到 {out} ({len(r.content)} bytes)")

# ── 4. 完整歌曲生成 (base64 JSON) ─────────────────────────────────────────────
print("\n[*] 完整歌曲生成 (INTRO→BUILD→DROP→OUTRO) ...")
song_payload = {
    "bpm": 128,
    "key": "A_MINOR",
    "segments": [
        {"name": "Intro",  "struct": "INTRO",  "bars": 8,  "e_level": 3, "tracks": ["DRUMS","BASS"]},
        {"name": "Build",  "struct": "BUILD",  "bars": 8,  "e_level": 6, "tracks": ["DRUMS","BASS","CHORD"]},
        {"name": "Drop",   "struct": "DROP",   "bars": 16, "e_level": 8, "tracks": ["DRUMS","BASS","CHORD","MELODY"]},
        {"name": "Outro",  "struct": "OUTRO",  "bars": 8,  "e_level": 2, "tracks": ["DRUMS","BASS"]},
    ],
    "max_new_tokens_per_segment": 600,
    "temperature": 0.85,
    "top_p": 0.92,
    "return_base64": True,
}
r = check(requests.post(f"{BASE}/generate/song", json=song_payload), "generate/song")
resp = r.json()
out = f"api/{resp['filename']}"
with open(out, "wb") as f:
    f.write(base64.b64decode(resp["midi_base64"]))
print(f"[OK] 保存到 {out} ({len(resp['midi_base64'])} chars base64)")
