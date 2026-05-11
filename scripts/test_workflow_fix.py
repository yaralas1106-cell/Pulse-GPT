"""Test workflow runs past reflect node without KeyError."""
import urllib.request, json

payload = json.dumps({"message": "生成一段 128BPM 的 House Drop", "session_id": "fix-test"}).encode()
req = urllib.request.Request(
    "http://localhost:7860/chat/stream",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
resp = urllib.request.urlopen(req, timeout=60)

seen_nodes = []
for line in resp:
    line = line.decode("utf-8").strip()
    if not line.startswith("data:"):
        continue
    try:
        e = json.loads(line[5:])
    except Exception:
        continue

    etype = e.get("type", "")
    name  = e.get("name", "")

    if etype == "tool_call":
        print(f"  -> {name}")
        seen_nodes.append(name)

    if etype == "error":
        print(f"  ERROR: {e.get('message','')[:200]}")
        break

    if etype == "done":
        print(f"  DONE  text={e.get('text','')[:80]}")
        break

    if len(seen_nodes) >= 10:
        print("  (stopping early, enough nodes seen)")
        break

print("\nNodes visited:", seen_nodes)
