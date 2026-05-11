# -*- coding: utf-8 -*-
import urllib.request, json, urllib.error

body = json.dumps(
    {"instruction": "39-49小节出现完全空白 帮我加入鼓组的pattern完善", "seed": 1},
    ensure_ascii=False
).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8002/chat_edit",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    r = urllib.request.urlopen(req, timeout=60)
    data = json.loads(r.read().decode())
    print("status:", data["status"])
    for item in data.get("results", []):
        ops = [o["op"] for o in item.get("ops_applied", [])]
        print(f"  {item['track']}  ops={ops}  notes:{item['notes_before']}->{item['notes_after']}  ableton={item['ableton_status']}")
except urllib.error.HTTPError as e:
    print("HTTP", e.code)
    print(e.read().decode()[:1000])
