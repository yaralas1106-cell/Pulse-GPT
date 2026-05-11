"""
PulseFormer Inference API
=========================
FastAPI service that wraps PulseCPFiLMGenerator.

Endpoints
---------
GET  /health                  - liveness check
GET  /model/info              - loaded model metadata
POST /generate/segment        - generate one structural segment → MIDI file
POST /generate/song           - generate full song from blueprint → MIDI file
"""

import io
import os
import sys
import base64
import tempfile
import traceback
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

# ── resolve project root so imports work regardless of cwd ───────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "data_pipeline"))
sys.path.insert(0, str(_ROOT / "inference"))

from inference.generate_cp import PulseCPGenerator  # noqa: E402

# ── app & global generator ────────────────────────────────────────────────────

app = FastAPI(
    title="PulseFormer API",
    version="1.0.0",
    description="Music generation API backed by PulseCPGenerator",
)

_gen: Optional[PulseCPGenerator] = None

DEFAULT_MODEL = str(_ROOT / "checkpoints/pulsecp_v5_clean_best.pt")
DEFAULT_VOCAB  = str(_ROOT / "dataset/processed/pulse_cp_vocab_5d_v5_clean.json")


def _get_generator() -> PulseCPGenerator:
    global _gen
    if _gen is None:
        raise HTTPException(status_code=503, detail="Model not loaded — call /model/load first")
    return _gen


# ── schemas ───────────────────────────────────────────────────────────────────

VALID_KEYS = [
    f"{n}_{s}"
    for n in ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    for s in ["MAJOR","MINOR"]
]

VALID_STRUCTS = ["INTRO","VERSE","BUILD","DROP","BREAK","OUTRO"]
VALID_TRACKS  = ["DRUMS","BASS","CHORD","MELODY"]


class LoadRequest(BaseModel):
    model_path: str = DEFAULT_MODEL
    vocab_path:  str = DEFAULT_VOCAB


class SegmentRequest(BaseModel):
    bpm:        float = Field(128.0, ge=60, le=220)
    key:        str   = Field("C_MAJOR", description=f"One of: {VALID_KEYS}")
    struct:     str   = Field("DROP", description=f"One of: {VALID_STRUCTS}")
    tracks:     List[str] = Field(["DRUMS","BASS","CHORD","MELODY"])
    e_level:    int   = Field(5, ge=1, le=8, description="Energy level 1–8 (scalar fallback)")
    energy_curve: Optional[List[int]] = Field(None, description="Per-bar E_level list; overrides e_level")
    bars:       int   = Field(16, ge=1, le=64)
    max_new_tokens: int   = Field(600, ge=50, le=4096)
    temperature:    float = Field(0.85, ge=0.1, le=2.0)
    top_p:          float = Field(0.92, ge=0.1, le=1.0)
    return_base64:  bool  = False


class RegenerateTrackRequest(BaseModel):
    bpm:         float = Field(128.0, ge=60, le=220)
    key:         str   = Field("C_MAJOR")
    struct:      str   = Field("DROP")
    target_track: str  = Field(..., description="Track to regenerate: DRUMS/BASS/CHORD/MELODY")
    locked_midi_base64: str = Field(..., description="Base64-encoded MIDI of the full arrangement to lock")
    e_level:     int   = Field(5, ge=1, le=8)
    energy_curve: Optional[List[int]] = None
    bars:        int   = Field(16, ge=1, le=64)
    max_new_tokens: int = Field(600, ge=50, le=4096)
    temperature:    float = Field(0.85, ge=0.1, le=2.0)
    top_p:          float = Field(0.92, ge=0.1, le=1.0)
    return_base64:  bool  = False


class EnergyRampRequest(BaseModel):
    start_energy: int = Field(..., ge=1, le=8)
    end_energy:   int = Field(..., ge=1, le=8)
    bars:         int = Field(..., ge=1, le=128)
    curve:        str = Field("linear", description="linear | exponential | s-curve")


class ArrangementRequest(BaseModel):
    bpm:      float = Field(128.0, ge=60, le=220)
    key:      str   = Field("C_MAJOR")
    structure: List[dict] = Field(
        ...,
        description='List of {name, bars, e_level, tracks} — e.g. [{"name":"Intro","bars":8,"e_level":2,"tracks":["DRUMS","BASS"]}]'
    )
    max_new_tokens_per_segment: int   = Field(600, ge=50, le=4096)
    temperature: float = Field(0.85, ge=0.1, le=2.0)
    top_p:       float = Field(0.92, ge=0.1, le=1.0)
    return_base64: bool = False


class SongSegment(BaseModel):
    name:    str
    struct:  str = Field("DROP", description=f"One of: {VALID_STRUCTS}")
    bars:    int = Field(16, ge=1, le=64)
    e_level: int = Field(5, ge=1, le=8)
    tracks:  List[str] = Field(["DRUMS","BASS","CHORD","MELODY"])


class SongRequest(BaseModel):
    bpm:      float = Field(128.0, ge=60, le=220)
    key:      str   = Field("C_MAJOR")
    segments: List[SongSegment]
    max_new_tokens_per_segment: int   = Field(600, ge=50, le=4096)
    temperature: float = Field(0.85, ge=0.1, le=2.0)
    top_p:       float = Field(0.92, ge=0.1, le=1.0)
    return_base64: bool = False


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_prompt(bpm: float, key: str, struct: str, tracks: List[str],
                  e_level: int, energy_curve: list = None) -> List[str]:
    effective_e = int(energy_curve[0]) if energy_curve else e_level
    tokens = [f"[BPM_{int(bpm)}]", f"[KEY_{key}]", f"[STRUCT_{struct}]",
              f"[ENERGY_LEVEL_{effective_e}]"]
    for t in VALID_TRACKS:
        if t in tracks:
            tokens.append(f"[HAS_{t}]")
    tokens.append("[BAR_START]")
    return tokens


def _midi_bytes(gen: PulseCPGenerator, notes_dict: dict,
                bpm: float, total_bars: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        gen.dicts_to_midi(notes_dict, bpm=bpm, struct_bars=total_bars, output_path=tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def _midi_response(midi_bytes: bytes, filename: str,
                   return_base64: bool) -> Response:
    if return_base64:
        return JSONResponse({"midi_base64": base64.b64encode(midi_bytes).decode(),
                             "filename": filename})
    return Response(
        content=midi_bytes,
        media_type="audio/midi",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _gen is not None}


@app.get("/model/info")
def model_info():
    gen = _get_generator()
    return {"device": str(gen.device), "model": DEFAULT_MODEL}


@app.post("/model/load")
def model_load(req: LoadRequest):
    global _gen
    try:
        _gen = PulseCPGenerator(
            model_path=req.model_path,
            vocab_path=req.vocab_path,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "loaded", "device": str(_gen.device)}


@app.post("/generate/segment")
def generate_segment(req: SegmentRequest):
    """Generate one structural segment and return a MIDI file."""
    gen = _get_generator()

    if req.key not in VALID_KEYS:
        raise HTTPException(400, f"key must be one of {VALID_KEYS}")
    if req.struct not in VALID_STRUCTS:
        raise HTTPException(400, f"struct must be one of {VALID_STRUCTS}")
    invalid_tracks = set(req.tracks) - set(VALID_TRACKS)
    if invalid_tracks:
        raise HTTPException(400, f"unknown tracks: {invalid_tracks}")

    try:
        prompt = _build_prompt(req.bpm, req.key, req.struct, req.tracks,
                               req.e_level, req.energy_curve)
        tokens = gen.generate(
            prompt_tokens=prompt,
            max_new_tokens=req.max_new_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
        notes_dict, bpm = gen.tokens_to_note_dicts(tokens, default_bpm=req.bpm)
        midi_data = _midi_bytes(gen, notes_dict, bpm=bpm, total_bars=req.bars)
    except Exception:
        raise HTTPException(500, traceback.format_exc())

    fname = f"pulseformer_{req.struct.lower()}_e{req.e_level}_{int(req.bpm)}bpm.mid"
    return _midi_response(midi_data, fname, req.return_base64)


# ── Atomic Tools ─────────────────────────────────────────────────────────────

@app.post("/tools/generate_section",
          summary="生成单个段落（Agent 原子工具）")
def tool_generate_section(req: SegmentRequest):
    """Generate one section (8–64 bars). Thin alias for /generate/segment."""
    return generate_segment(req)


@app.post("/tools/generate_arrangement",
          summary="生成完整编曲（Ramp Scheduler）")
def tool_generate_arrangement(req: ArrangementRequest):
    """
    Given a structure list, generate each section and stitch into one MIDI.
    Equivalent to calling generate_section for each segment and time-offsetting.
    """
    gen = _get_generator()

    if req.key not in VALID_KEYS:
        raise HTTPException(400, f"key must be one of {VALID_KEYS}")

    try:
        global_notes: dict = defaultdict(list)
        offset_beats  = 0.0
        total_bars    = 0

        for i, seg in enumerate(req.structure):
            name   = seg.get("name", f"seg{i}")
            struct = seg.get("struct", seg.get("name", "DROP")).upper()
            bars   = int(seg.get("bars", 16))
            e_lvl  = int(seg.get("e_level", 5))
            tracks = seg.get("tracks", VALID_TRACKS)
            e_curve= seg.get("energy_curve", None)

            if struct not in VALID_STRUCTS:
                struct = "DROP"

            prompt = _build_prompt(req.bpm, req.key, struct, tracks, e_lvl, e_curve)
            tokens = gen.generate(
                prompt_tokens=prompt,
                max_new_tokens=req.max_new_tokens_per_segment,
                temperature=req.temperature,
                top_p=req.top_p,
            )
            notes_dict, _ = gen.tokens_to_note_dicts(tokens, default_bpm=req.bpm)

            seg_beats = bars * 4.0
            for track, notes in notes_dict.items():
                for note in notes:
                    if note["start_time"] >= seg_beats:
                        continue
                    if note["start_time"] + note["duration"] > seg_beats:
                        note["duration"] = seg_beats - note["start_time"]
                    note["start_time"] += offset_beats
                    global_notes[track].append(note)

            offset_beats += seg_beats
            total_bars   += bars

        midi_data = _midi_bytes(gen, dict(global_notes), bpm=req.bpm, total_bars=total_bars)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, traceback.format_exc())

    fname = f"pulseformer_arrangement_{int(req.bpm)}bpm_{req.key.lower()}.mid"
    return _midi_response(midi_data, fname, req.return_base64)


@app.post("/tools/apply_energy_ramp",
          summary="生成 per-bar 能量插值曲线（纯计算，无需模型）")
def tool_apply_energy_ramp(req: EnergyRampRequest):
    """
    Compute an interpolated energy curve from start to end over N bars.
    Returns a list of integers you can pass as energy_curve to other endpoints.
    """
    import math
    n = req.bars
    s, e = req.start_energy, req.end_energy

    if req.curve == "linear":
        curve = [round(s + (e - s) * i / max(n - 1, 1)) for i in range(n)]
    elif req.curve == "exponential":
        curve = [round(s * ((e / max(s, 1)) ** (i / max(n - 1, 1)))) for i in range(n)]
        curve = [max(1, min(8, v)) for v in curve]
    elif req.curve == "s-curve":
        curve = []
        for i in range(n):
            t = i / max(n - 1, 1)
            t_s = t * t * (3 - 2 * t)  # smoothstep
            curve.append(round(s + (e - s) * t_s))
    else:
        raise HTTPException(400, f"curve must be linear | exponential | s-curve")

    curve = [max(1, min(8, v)) for v in curve]
    return {"bars": n, "curve_type": req.curve, "energy_curve": curve}


@app.post("/tools/regenerate_track",
          summary="锁定其他轨道，只重生成指定轨（Agent 原子工具）")
def tool_regenerate_track(req: RegenerateTrackRequest):
    """
    Re-generate one track while keeping all others unchanged.
    Pass the existing arrangement as base64 MIDI; get back a new MIDI
    with only the target track replaced.
    """
    gen = _get_generator()

    if req.target_track not in VALID_TRACKS:
        raise HTTPException(400, f"target_track must be one of {VALID_TRACKS}")
    if req.key not in VALID_KEYS:
        raise HTTPException(400, f"key must be one of {VALID_KEYS}")

    # Decode locked MIDI → note dicts
    try:
        midi_bytes_in = base64.b64decode(req.locked_midi_base64)
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
            tmp.write(midi_bytes_in)
            tmp_path = tmp.name
        locked_pm = pretty_midi.PrettyMIDI(tmp_path)
        os.unlink(tmp_path)
    except Exception:
        raise HTTPException(400, f"Invalid locked_midi_base64: {traceback.format_exc()}")

    # Extract locked tracks as note dicts
    track_name_map = {"DRUMS": 9, "BASS": 0, "CHORD": 1, "MELODY": 2}
    locked_notes: dict = {"DRUMS": [], "BASS": [], "CHORD": [], "MELODY": []}
    beats_per_sec = req.bpm / 60.0
    for inst in locked_pm.instruments:
        for track, ch in track_name_map.items():
            if track == req.target_track:
                continue
            if (track == "DRUMS" and inst.is_drum) or (track != "DRUMS" and inst.program == ch):
                for n in inst.notes:
                    locked_notes[track].append({
                        "pitch": n.pitch,
                        "start_time": n.start * beats_per_sec,
                        "duration":   (n.end - n.start) * beats_per_sec,
                        "velocity":   n.velocity,
                        "mute": False,
                        "energy": req.e_level,
                    })

    # Generate only the target track
    prompt = _build_prompt(req.bpm, req.key, req.struct,
                           [req.target_track], req.e_level, req.energy_curve)
    try:
        tokens = gen.generate(
            prompt_tokens=prompt,
            max_new_tokens=req.max_new_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
        )
        new_notes, _ = gen.tokens_to_note_dicts(tokens, default_bpm=req.bpm)
    except Exception:
        raise HTTPException(500, traceback.format_exc())

    # Merge: locked tracks + new target track
    merged = {t: (locked_notes[t] if t != req.target_track else new_notes[t])
              for t in VALID_TRACKS}

    try:
        midi_data = _midi_bytes(gen, merged, bpm=req.bpm, total_bars=req.bars)
    except Exception:
        raise HTTPException(500, traceback.format_exc())

    fname = f"pulseformer_regen_{req.target_track.lower()}_{int(req.bpm)}bpm.mid"
    return _midi_response(midi_data, fname, req.return_base64)


@app.post("/generate/song")
def generate_song(req: SongRequest):
    """Generate a full multi-segment song and return a single stitched MIDI file."""
    gen = _get_generator()

    if req.key not in VALID_KEYS:
        raise HTTPException(400, f"key must be one of {VALID_KEYS}")
    if not req.segments:
        raise HTTPException(400, "segments list is empty")

    try:
        global_notes: dict = defaultdict(list)
        offset_beats  = 0.0
        total_bars    = sum(s.bars for s in req.segments)

        for i, seg in enumerate(req.segments):
            if seg.struct not in VALID_STRUCTS:
                raise HTTPException(400, f"segment {i}: unknown struct '{seg.struct}'")

            prompt = _build_prompt(req.bpm, req.key, seg.struct, seg.tracks, seg.e_level)
            tokens = gen.generate(
                prompt_tokens=prompt,
                max_new_tokens=req.max_new_tokens_per_segment,
                temperature=req.temperature,
                top_p=req.top_p,
            )
            notes_dict, _ = gen.tokens_to_note_dicts(tokens, default_bpm=req.bpm)

            seg_max_beats = seg.bars * 4.0
            for track, notes in notes_dict.items():
                for note in notes:
                    if note["start_time"] >= seg_max_beats:
                        continue
                    if note["start_time"] + note["duration"] > seg_max_beats:
                        note["duration"] = seg_max_beats - note["start_time"]
                    note["start_time"] += offset_beats
                    global_notes[track].append(note)

            offset_beats += seg_max_beats

        midi_data = _midi_bytes(gen, dict(global_notes), bpm=req.bpm, total_bars=total_bars)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, traceback.format_exc())

    fname = f"pulseformer_song_{int(req.bpm)}bpm_{req.key.lower()}.mid"
    return _midi_response(midi_data, fname, req.return_base64)


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="PulseFormer inference API server")
    parser.add_argument("--host",       default="0.0.0.0")
    parser.add_argument("--port",       type=int, default=8000)
    parser.add_argument("--model_path", default=DEFAULT_MODEL)
    parser.add_argument("--vocab_path", default=DEFAULT_VOCAB)
    args = parser.parse_args()

    print(f"[API] Loading model from {args.model_path} ...")
    _gen = PulseCPGenerator(
        model_path=args.model_path,
        vocab_path=args.vocab_path,
    )
    print(f"[API] Model ready on {_gen.device}. Listening on {args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)
