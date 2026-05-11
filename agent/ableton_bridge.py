"""
agent/ableton_bridge.py
=======================
FastAPI bridge (port 8002) between TOMI Agent and Ableton Live socket RPC (port 9877).

Endpoints:
  POST /setup_edm_template   — create 4-track EDM template + set BPM
  POST /import_stems         — import PulseFormer multi-track MIDI into Ableton
  POST /llm_edit             — LLM-driven note editing for a specific track
  POST /apply_sidechain      — configure sidechain compression
  GET  /health               — connectivity check (tests socket to Ableton)
  GET  /state                — return current in-memory track state
"""

import base64
import json
import socket
import sys
import tempfile
import os
import traceback
from pathlib import Path

# ensure project root is on sys.path when run as a script
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pretty_midi
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent.llm_ableton_editor import ask_llm_for_ops, ask_llm_chat_edit, apply_ops

app = FastAPI(title="TOMI Ableton Bridge", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── In-memory track state (populated by import_stems) ────────────────────────
# Format: { "TOMI-DRUMS": {"notes": [...], "track_index": int,
#                           "view_mode": str, "clip_length": float,
#                           "bpm": float, "key": str} }
_track_state: dict[str, dict] = {}

_STATE_FILE = _ROOT / "data" / "bridge_state.json"


def _save_state():
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(_track_state), encoding="utf-8")
    except Exception:
        pass


def _load_state():
    global _track_state
    if _STATE_FILE.exists():
        try:
            _track_state = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass


_load_state()

ABLETON_HOST = "localhost"
ABLETON_PORT = 9877
SOCKET_TIMEOUT = 15.0

# ── Ableton RPC ───────────────────────────────────────────────────────────────

def _rpc(cmd: str, params: dict = None) -> dict:
    """Send one JSON-RPC command to Ableton Remote Script and return result."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(SOCKET_TIMEOUT)
    try:
        s.connect((ABLETON_HOST, ABLETON_PORT))
        payload = json.dumps({"type": cmd, "params": params or {}})
        s.sendall(payload.encode("utf-8"))
        data = b""
        while True:
            try:
                chunk = s.recv(8192)
                if not chunk:
                    break
                data += chunk
                try:
                    res = json.loads(data.decode("utf-8"))
                    if res.get("status") == "error":
                        raise RuntimeError(res.get("message", "Ableton RPC error"))
                    return res.get("result", {})
                except json.JSONDecodeError:
                    continue
            except socket.timeout:
                break
        return {}
    finally:
        s.close()


def _check_connection():
    try:
        _rpc("get_session_info")
        return True
    except Exception:
        return False


# ── Schemas ───────────────────────────────────────────────────────────────────

TRACK_ORDER  = ["DRUMS", "BASS", "CHORD", "MELODY"]
TRACK_COLORS = {"DRUMS": 8, "BASS": 9, "CHORD": 10, "MELODY": 11}
TRACK_INSTRUMENTS = {
    "DRUMS":  {"type": "drum_rack",  "uri": "Drums/Drum Rack"},
    "BASS":   {"type": "instrument", "uri": "query:Synths#Instrument%20Rack:Bass"},
    "CHORD":  {"type": "instrument", "uri": "query:Synths#Instrument%20Rack:Pad"},
    "MELODY": {"type": "instrument", "uri": "query:Synths#Instrument%20Rack:Lead"},
}


class TemplateRequest(BaseModel):
    bpm: float = 128.0
    key: str   = "C_MAJOR"


class ImportStemsRequest(BaseModel):
    midi_base64: str
    view_mode:   str   = "arrange"
    key:         str   = "C_MINOR"   # passed through to track state for LLM context


class LLMEditRequest(BaseModel):
    track_name:  str          # e.g. "TOMI-MELODY" or "all"
    instruction: str          # natural language: "make the bass more aggressive"
    seed:        int  = 0


class ChatEditRequest(BaseModel):
    instruction: str   # free-form, any language — LLM decides which tracks + ops
    seed:        int = 0


class SidechainRequest(BaseModel):
    source_track: str
    target_track:  str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    connected = _check_connection()
    return {"status": "ok" if connected else "ableton_offline",
            "ableton_connected": connected}


@app.post("/setup_edm_template")
def setup_edm_template(req: TemplateRequest):
    """Create 4-track EDM template in Ableton and set BPM."""
    if not _check_connection():
        raise HTTPException(503, "Ableton Live not reachable on port 9877. "
                                 "请确认 Ableton 已运行且 Remote Script 已加载。")
    try:
        _rpc("set_tempo", {"tempo": req.bpm})
        created = []
        for name in TRACK_ORDER:
            result  = _rpc("create_midi_track", {"index": -1})
            t_idx   = result.get("index", -1)
            _rpc("set_track_name", {"track_index": t_idx, "name": f"TOMI-{name}"})
            # Instrument loading is best-effort (depends on Remote Script version)
            try:
                inst = TRACK_INSTRUMENTS[name]
                if inst["type"] == "drum_rack":
                    _rpc("load_drum_rack", {"track_index": t_idx, "rack_uri": inst["uri"]})
                else:
                    _rpc("load_browser_item", {"track_index": t_idx, "item_uri": inst["uri"]})
            except Exception:
                pass
            created.append({"track": name, "index": t_idx})

        return {"status": "ok", "bpm": req.bpm, "tracks": created}
    except Exception:
        raise HTTPException(500, traceback.format_exc())


@app.post("/import_stems")
def import_stems(req: ImportStemsRequest):
    """Decode base64 MIDI, split by track, inject into Ableton."""
    if not _check_connection():
        raise HTTPException(503, "Ableton Live not reachable on port 9877.")

    # Decode MIDI
    try:
        midi_bytes = base64.b64decode(req.midi_base64)
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
            tmp.write(midi_bytes)
            tmp_path = tmp.name
        pm = pretty_midi.PrettyMIDI(tmp_path)
        os.unlink(tmp_path)
    except Exception:
        raise HTTPException(400, f"Invalid MIDI: {traceback.format_exc()}")

    # Use first tempo from MIDI tempo map (estimate_tempo() can be 2x off)
    tempo_times, tempos = pm.get_tempo_changes()
    bpm = float(tempos[0]) if len(tempos) > 0 else 128.0
    _rpc("set_tempo", {"tempo": round(bpm)})

    beats_per_sec = bpm / 60.0  # seconds → beats

    # PulseFormer names instruments by role: 'DRUMS', 'BASS', 'CHORD', 'MELODY'
    # Fall back to channel mapping for non-PulseFormer MIDI files
    ch_to_track = {9: "DRUMS", 0: "BASS", 1: "CHORD", 2: "MELODY"}
    name_to_track = {t: t for t in TRACK_ORDER}
    track_notes: dict = {t: [] for t in TRACK_ORDER}

    for inst in pm.instruments:
        if inst.is_drum:
            tname = "DRUMS"
        elif inst.name.upper() in name_to_track:
            tname = name_to_track[inst.name.upper()]
        elif inst.program in ch_to_track:
            tname = ch_to_track[inst.program]
        else:
            tname = None
        if tname is None:
            continue
        for n in inst.notes:
            track_notes[tname].append({
                "pitch":      n.pitch,
                "start_time": round(n.start * beats_per_sec, 4),
                "duration":   round((n.end - n.start) * beats_per_sec, 4),
                "velocity":   n.velocity,
            })

    # clip_length in beats
    all_notes = [n for notes in track_notes.values() for n in notes]
    clip_length = max(n["start_time"] + n["duration"] for n in all_notes) if all_notes else 16.0

    injected = []
    for name in TRACK_ORDER:
        notes = track_notes[name]
        if not notes:
            continue
        result = _rpc("create_midi_track", {"index": -1})
        t_idx  = result.get("index", -1)
        _rpc("set_track_name", {"track_index": t_idx, "name": f"TOMI-{name}"})

        # Instrument loading best-effort
        try:
            inst = TRACK_INSTRUMENTS[name]
            if inst["type"] == "drum_rack":
                _rpc("load_drum_rack", {"track_index": t_idx, "rack_uri": inst["uri"]})
            else:
                _rpc("load_browser_item", {"track_index": t_idx, "item_uri": inst["uri"]})
        except Exception:
            pass

        if req.view_mode == "session":
            _rpc("create_clip", {"track_index": t_idx, "clip_index": 0,
                                 "length": clip_length})
            for i in range(0, len(notes), 500):
                _rpc("add_notes_to_clip",
                     {"track_index": t_idx, "clip_index": 0,
                      "notes": notes[i:i+500]})
            _rpc("set_clip_name", {"track_index": t_idx, "clip_index": 0,
                                   "name": f"TOMI-{name}"})
        else:
            _rpc("create_arrangement_clip",
                 {"track_index": t_idx, "position": 0.0, "length": clip_length})
            for i in range(0, len(notes), 500):
                _rpc("add_notes_to_arrangement_clip",
                     {"track_index": t_idx, "clip_index": 0,
                      "notes": notes[i:i+500]})

        # Save to track state for LLM editing
        _track_state[f"TOMI-{name}"] = {
            "notes":       notes,
            "track_index": t_idx,
            "clip_index":  0,
            "view_mode":   req.view_mode,
            "clip_length": clip_length,
            "bpm":         round(bpm),
            "key":         req.key,
            "is_drum":     (name == "DRUMS"),
        }
        injected.append({"track": name, "notes": len(notes), "index": t_idx})

    _save_state()
    return {"status": "ok", "bpm": round(bpm), "injected": injected,
            "view_mode": req.view_mode}


# ── LLM Edit ──────────────────────────────────────────────────────────────────

@app.get("/state")
def get_state():
    """Return summary of current in-memory track state."""
    summary = {}
    for track_name, info in _track_state.items():
        summary[track_name] = {
            "notes":       len(info["notes"]),
            "track_index": info["track_index"],
            "view_mode":   info["view_mode"],
            "bpm":         info["bpm"],
            "key":         info["key"],
        }
    return {"tracks": summary}


@app.post("/llm_edit")
def llm_edit(req: LLMEditRequest):
    """
    Use the LLM to modify notes for one or all tracks, then re-inject into Ableton.

    track_name: "TOMI-MELODY" | "TOMI-DRUMS" | "TOMI-BASS" | "TOMI-CHORD" | "all"
    instruction: free-form natural language edit request
    """
    if not _check_connection():
        raise HTTPException(503, "Ableton Live not reachable on port 9877.")

    if not _track_state:
        raise HTTPException(400, "No track state found. Call /import_stems first.")

    # Determine which tracks to edit
    if req.track_name == "all":
        targets = list(_track_state.keys())
    elif req.track_name in _track_state:
        targets = [req.track_name]
    else:
        raise HTTPException(404, f"Track '{req.track_name}' not in state. "
                                 f"Available: {list(_track_state.keys())}")

    results = []
    for track_name in targets:
        info = _track_state[track_name]
        notes_before = info["notes"]
        bpm          = info["bpm"]
        key          = info["key"]
        is_drum      = info["is_drum"]
        t_idx        = info["track_index"]
        clip_idx     = info["clip_index"]
        view_mode    = info["view_mode"]

        # Ask LLM for operations
        try:
            ops, llm_raw = ask_llm_for_ops(
                track_name=track_name,
                notes=notes_before,
                instruction=req.instruction,
                bpm=bpm,
                key=key,
                is_drum=is_drum,
            )
        except Exception:
            raise HTTPException(500, f"LLM call failed: {traceback.format_exc()}")

        if not ops:
            results.append({
                "track": track_name,
                "status": "no_ops",
                "llm_response": llm_raw,
            })
            continue

        # Apply operations
        notes_after = apply_ops(notes_before, ops, seed=req.seed)

        # Re-inject into Ableton (set_notes replaces existing notes)
        try:
            if view_mode == "session":
                _rpc("add_notes_to_clip",
                     {"track_index": t_idx, "clip_index": clip_idx,
                      "notes": notes_after})
            else:
                _rpc("add_notes_to_arrangement_clip",
                     {"track_index": t_idx, "clip_index": clip_idx,
                      "notes": notes_after})
        except Exception:
            raise HTTPException(500, f"Ableton inject failed: {traceback.format_exc()}")

        # Update state
        _track_state[track_name]["notes"] = notes_after
        _save_state()

        results.append({
            "track":        track_name,
            "status":       "ok",
            "ops_applied":  ops,
            "notes_before": len(notes_before),
            "notes_after":  len(notes_after),
            "track_index":  t_idx,
        })

    return {"status": "ok", "results": results}


@app.post("/chat_edit")
def chat_edit(req: ChatEditRequest):
    """
    Free-form natural language edit: LLM decides which tracks to modify and what operations to apply.
    Works on whatever tracks are currently in _track_state (populated by /import_stems).
    """
    if not _track_state:
        raise HTTPException(400, "No track state found. Call /import_stems first.")

    ableton_connected = _check_connection()

    # Build per-track context for the LLM
    track_context = {
        tname: {
            "notes":   info["notes"],
            "bpm":     info["bpm"],
            "key":     info["key"],
            "is_drum": info["is_drum"],
        }
        for tname, info in _track_state.items()
    }

    # Single LLM call: decides tracks + ops
    try:
        edits, llm_raw = ask_llm_chat_edit(track_context, req.instruction)
    except Exception:
        raise HTTPException(500, f"LLM call failed:\n{traceback.format_exc()}")

    if not edits:
        return {"status": "no_edits", "llm_response": llm_raw,
                "instruction": req.instruction}

    results = []
    for edit in edits:
        track_name = edit.get("track", "")
        ops        = edit.get("ops", [])

        if track_name not in _track_state:
            results.append({"track": track_name, "status": "unknown_track"})
            continue
        if not ops:
            results.append({"track": track_name, "status": "no_ops"})
            continue

        info         = _track_state[track_name]
        notes_before = info["notes"]
        notes_after  = apply_ops(notes_before, ops, seed=req.seed)

        ableton_status = "skipped_offline"
        if ableton_connected:
            try:
                cmd = ("add_notes_to_clip" if info.get("view_mode") == "session"
                       else "add_notes_to_arrangement_clip")
                # Compute required clip length to fit all notes
                if notes_after:
                    required_len = max(
                        n["start_time"] + n["duration"] for n in notes_after
                    )
                    current_len = info.get("clip_length", 32.0)
                    if required_len > current_len:
                        try:
                            _rpc("set_clip_length", {
                                "track_index": info["track_index"],
                                "clip_index":  info.get("clip_index", 0),
                                "length":      required_len,
                            })
                            _track_state[track_name]["clip_length"] = required_len
                        except Exception:
                            pass  # best-effort; clip may truncate notes
                _rpc(cmd, {"track_index": info["track_index"],
                           "clip_index":  info.get("clip_index", 0),
                           "notes":       notes_after})
                ableton_status = "injected"
            except Exception:
                ableton_status = f"inject_error: {traceback.format_exc()[:200]}"

        _track_state[track_name]["notes"] = notes_after
        results.append({
            "track":          track_name,
            "status":         "ok",
            "ops_applied":    ops,
            "notes_before":   len(notes_before),
            "notes_after":    len(notes_after),
            "ableton_status": ableton_status,
        })

    _save_state()
    return {
        "status":      "ok",
        "instruction": req.instruction,
        "results":     results,
    }


@app.post("/apply_sidechain")
def apply_sidechain(req: SidechainRequest):
    """Add Compressor to target_track and route sidechain from source_track."""
    if not _check_connection():
        raise HTTPException(503, "Ableton Live not reachable on port 9877.")
    try:
        # Find track indices by name
        tracks_info = _rpc("get_track_info", {})
        name_to_idx = {}
        for t in (tracks_info if isinstance(tracks_info, list) else []):
            name_to_idx[t.get("name", "")] = t.get("index")

        src_idx = name_to_idx.get(req.source_track)
        tgt_idx = name_to_idx.get(req.target_track)

        if src_idx is None:
            raise HTTPException(400, f"源轨道未找到: {req.source_track}")
        if tgt_idx is None:
            raise HTTPException(400, f"目标轨道未找到: {req.target_track}")

        # Load Compressor on target track
        _rpc("load_instrument_or_effect", {
            "track_index": tgt_idx,
            "uri": "query:Audio%20Effects#Compressor",
        })

        # Enable sidechain — Ableton API exposes this via device parameter
        _rpc("set_device_parameter", {
            "track_index":  tgt_idx,
            "device_index": -1,          # last device = the Compressor we just added
            "param_name":   "Sidechain",
            "value":        1,
        })
        _rpc("set_device_parameter", {
            "track_index":  tgt_idx,
            "device_index": -1,
            "param_name":   "Sidechain Input",
            "value":        src_idx,
        })

        return {
            "status": "ok",
            "source": req.source_track,
            "target": req.target_track,
            "note": "Compressor 已添加并配置侧链路由",
        }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, traceback.format_exc())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("agent.ableton_bridge:app", host="0.0.0.0", port=8002, reload=False)
