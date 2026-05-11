"""
agent/web_server.py
===================
FastAPI 服务：聊天 API + 静态文件 + 音频/MIDI 下载

启动：
    python agent/web_server.py
    # 或
    C:\\Users\\YaRa\\anaconda3\\python.exe -m uvicorn agent.web_server:app --port 7860 --reload
"""

import sys
import uuid
import json
import httpx
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── project root on sys.path ──────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent.agent import MusicAgent
from agent.workflow import run_stream_v2
from agent.tools import AUDIO_DIR, MIDI_DIR

app = FastAPI(title="TOMI Music Agent", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── global agent instance (legacy /chat) ──────────────────────────────────────
_agent = MusicAgent()


# ── schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    session_id: str = ""
    message: str


class ChatResponse(BaseModel):
    session_id: str
    text: str
    audio_url: str | None = None
    midi_url: str | None = None


# ── routes ────────────────────────────────────────────────────────────────────

_SHOWCASE_FILE = _ROOT / "agent" / "static" / "showcase.html"
_CHAT_FILE = _ROOT / "agent" / "static" / "chat.html"

@app.get("/", response_class=HTMLResponse)
@app.get("/showcase", response_class=HTMLResponse)
def showcase():
    if _SHOWCASE_FILE.exists():
        return HTMLResponse(_SHOWCASE_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>showcase.html not found</h1>", status_code=404)


@app.get("/chat-ui", response_class=HTMLResponse)
def chat_ui():
    if _CHAT_FILE.exists():
        return HTMLResponse(_CHAT_FILE.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>chat.html not found</h1>", status_code=404)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())[:8]
    try:
        result = _agent.chat(session_id, req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(
        session_id=session_id,
        text=result["text"],
        audio_url=result["audio_url"],
        midi_url=result["midi_url"],
    )


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE endpoint — LangGraph workflow, streams node/tool events in real time."""
    session_id = req.session_id or str(uuid.uuid4())[:8]

    def event_gen():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session_id})}\n\n"
        for chunk in run_stream_v2(session_id, req.message):
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no",
                                      "Cache-Control": "no-cache"})


@app.delete("/session/{session_id}")
def reset_session(session_id: str):
    _agent.reset_session(session_id)
    return {"status": "reset"}


# ── Ableton edit proxy ────────────────────────────────────────────────────────

ABLETON_BRIDGE = "http://localhost:8002"


class AbletonEditRequest(BaseModel):
    instruction: str
    seed: int = 0


@app.get("/ableton/state")
def ableton_state():
    """Proxy: current track state from ableton_bridge."""
    try:
        r = httpx.get(f"{ABLETON_BRIDGE}/state", timeout=5)
        return r.json()
    except Exception as e:
        raise HTTPException(503, f"Ableton bridge unreachable: {e}")


@app.post("/ableton/edit")
def ableton_edit(req: AbletonEditRequest):
    """Proxy: free-form natural language → ableton_bridge /chat_edit."""
    try:
        r = httpx.post(
            f"{ABLETON_BRIDGE}/chat_edit",
            json={"instruction": req.instruction, "seed": req.seed},
            timeout=60,
        )
        return r.json()
    except Exception as e:
        raise HTTPException(503, f"Ableton bridge unreachable: {e}")


@app.get("/audio/{filename}")
def serve_audio(filename: str):
    # Support both .mp3 and .wav and .mid
    for ext in [".mp3", ".wav", ".mid"]:
        stem = filename.replace(".mp3", "").replace(".wav", "").replace(".mid", "")
        path = AUDIO_DIR / f"{stem}{ext}"
        if path.exists():
            media_type = {
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".mid": "audio/midi",
            }[ext]
            return FileResponse(str(path), media_type=media_type)
    raise HTTPException(status_code=404, detail="Audio file not found")


@app.get("/midi/{file_id}")
def serve_midi(file_id: str):
    path = MIDI_DIR / f"{file_id}.mid"
    if not path.exists():
        raise HTTPException(status_code=404, detail="MIDI file not found")
    return FileResponse(str(path), media_type="audio/midi",
                        headers={"Content-Disposition": f'attachment; filename="{file_id}.mid"'})


# ── serve frontend ─────────────────────────────────────────────────────────────
_WEB_DIR = _ROOT / "web"
if _WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIR), html=True), name="static")


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.web_server:app", host="0.0.0.0", port=7860, reload=True)
