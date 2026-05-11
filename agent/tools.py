"""
agent/tools.py
==============
Tool function implementations + Claude API tool_use schema definitions.

Each tool has:
  - SCHEMA dict  → passed to Claude as tools=[...]
  - execute(input) function → called when Claude requests the tool

Tool flow:
  plan_song → generate_music → render_audio
  recall_memory / update_memory (any time)
"""

import json
import os
import uuid
import base64
import tempfile
import traceback
import httpx
from pathlib import Path
from typing import Any

# ── config ─────────────────────────────────────────────────────────────────────

PULSEFORMER_API = os.environ.get("PULSEFORMER_API", "http://localhost:8000")
RAG_API         = os.environ.get("RAG_API",         "http://localhost:8001")
ABLETON_API     = os.environ.get("ABLETON_API",     "http://localhost:8002")  # ableton-mcp bridge

AUDIO_DIR = Path(__file__).parent / "audio_cache"
MIDI_DIR  = Path(__file__).parent / "midi_cache"

AUDIO_DIR.mkdir(exist_ok=True)
MIDI_DIR.mkdir(exist_ok=True)

VALID_STRUCTS = ["INTRO", "VERSE", "BUILD", "DROP", "BREAK", "OUTRO"]
VALID_KEYS    = [
    f"{n}_{s}"
    for n in ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    for s in ["MAJOR","MINOR"]
]
VALID_TRACKS  = ["DRUMS","BASS","CHORD","MELODY"]

# ── Claude tool schemas ────────────────────────────────────────────────────────

PLAN_SONG_SCHEMA = {
    "name": "plan_song",
    "description": (
        "根据用户的自然语言描述，规划完整歌曲蓝图（BPM、调性、段落结构、乐器、能量级别）。"
        "返回结构化的 blueprint JSON，供 generate_music 使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "用户对音乐的描述，如 '140BPM的EDM Drop，A小调，充满能量'",
            },
            "style_hints": {
                "type": "object",
                "description": "来自用户记忆的风格偏好，可为空 {}",
                "properties": {
                    "preferred_bpm":   {"type": "number"},
                    "preferred_key":   {"type": "string"},
                    "preferred_style": {"type": "string"},
                },
            },
        },
        "required": ["description"],
    },
}

GENERATE_MUSIC_SCHEMA = {
    "name": "generate_music",
    "description": (
        "调用 PulseFormer API，根据歌曲蓝图生成 MIDI 文件。"
        "返回 midi_file_id，供 render_audio 使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "blueprint": {
                "type": "object",
                "description": "plan_song 返回的蓝图",
                "properties": {
                    "bpm":  {"type": "number", "minimum": 60, "maximum": 220},
                    "key":  {"type": "string", "description": f"One of: {VALID_KEYS}"},
                    "segments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name":    {"type": "string"},
                                "struct":  {"type": "string", "enum": VALID_STRUCTS},
                                "bars":    {"type": "integer", "minimum": 4, "maximum": 64},
                                "e_level": {"type": "integer", "minimum": 1, "maximum": 8},
                                "tracks":  {
                                    "type": "array",
                                    "items": {"type": "string", "enum": VALID_TRACKS},
                                },
                            },
                            "required": ["name","struct","bars","e_level"],
                        },
                    },
                    "temperature": {"type": "number", "minimum": 0.1, "maximum": 2.0},
                    "top_p":       {"type": "number", "minimum": 0.1, "maximum": 1.0},
                },
                "required": ["bpm","key","segments"],
            }
        },
        "required": ["blueprint"],
    },
}

RENDER_AUDIO_SCHEMA = {
    "name": "render_audio",
    "description": (
        "将 MIDI 文件渲染为 MP3 音频，返回可在浏览器播放的 audio_file_id。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "midi_file_id": {
                "type": "string",
                "description": "generate_music 返回的 MIDI 文件 ID",
            }
        },
        "required": ["midi_file_id"],
    },
}

RECALL_MEMORY_SCHEMA = {
    "name": "recall_memory",
    "description": "查询当前用户的音乐偏好记忆（BPM、风格、调性历史等）。",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

UPDATE_MEMORY_SCHEMA = {
    "name": "update_memory",
    "description": "保存或更新用户的音乐偏好，如 BPM 偏好、风格、喜欢的调性。",
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "偏好键名，如 preferred_bpm / preferred_key / preferred_style / liked_songs",
            },
            "value": {
                "description": "偏好值，可为字符串、数字或列表",
            },
        },
        "required": ["key","value"],
    },
}

ASK_KNOWLEDGE_SCHEMA = {
    "name": "ask_knowledge",
    "description": (
        "查询音乐知识库（RAG）。适用于：咨询侧链压缩、EQ、混音技巧、Ableton 操作、"
        "PulseFormer 论文内容等专业问题。返回知识库检索结果。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要查询的问题，如 '侧链压缩怎么配置' 或 'PulseFormer 的 Time-Major tokenization'",
            },
            "top_k": {
                "type": "integer",
                "description": "返回的知识片段数量，默认 3",
                "default": 3,
            },
        },
        "required": ["query"],
    },
}

REGENERATE_TRACK_SCHEMA = {
    "name": "regenerate_track",
    "description": (
        "锁定现有编曲中的其他轨道，只重新生成指定轨道。"
        "适用于：'鼓不变，换个 bass'、'保留其他，重做旋律' 等修改请求。"
        "需要提供当前 MIDI 的 file_id 和目标轨道名称。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "midi_file_id": {
                "type": "string",
                "description": "当前 MIDI 文件 ID（generate_music 返回的）",
            },
            "target_track": {
                "type": "string",
                "enum": VALID_TRACKS,
                "description": "要重新生成的轨道",
            },
            "bpm":    {"type": "number", "minimum": 60, "maximum": 220},
            "key":    {"type": "string"},
            "struct": {"type": "string", "enum": VALID_STRUCTS},
            "e_level":{"type": "integer", "minimum": 1, "maximum": 8},
            "bars":   {"type": "integer", "minimum": 4, "maximum": 64},
        },
        "required": ["midi_file_id", "target_track", "bpm", "key", "struct"],
    },
}

SETUP_ABLETON_TEMPLATE_SCHEMA = {
    "name": "setup_ableton_template",
    "description": (
        "在 Ableton Live 中一键创建 EDM 标准模板：4 轨（Kick/Bass/Chord/Lead）+ 默认音色 + 设置 BPM。"
        "需要 Ableton Live 正在运行且 ableton-mcp 已连接。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "bpm": {"type": "number", "minimum": 60, "maximum": 220, "description": "目标 BPM"},
            "key": {"type": "string", "description": "调性，如 A_MINOR"},
        },
        "required": ["bpm"],
    },
}

IMPORT_STEMS_TO_ABLETON_SCHEMA = {
    "name": "import_stems_to_ableton",
    "description": (
        "把 PulseFormer 生成的多轨 MIDI 自动路由到 Ableton 对应轨道。"
        "会自动匹配 DRUMS→鼓轨、BASS→Bass轨、CHORD→Chord轨、MELODY→Lead轨。"
        "需要先调用 setup_ableton_template 或手动建好轨道。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "midi_file_id": {
                "type": "string",
                "description": "generate_music 或 regenerate_track 返回的 MIDI 文件 ID",
            },
            "view_mode": {
                "type": "string",
                "enum": ["session", "arrange"],
                "description": "导入到 Session View 还是 Arrangement View",
                "default": "arrange",
            },
        },
        "required": ["midi_file_id"],
    },
}

APPLY_SIDECHAIN_SCHEMA = {
    "name": "apply_sidechain",
    "description": (
        "在 Ableton 中配置侧链压缩：在 target_track 上加 Compressor，"
        "信号源设为 source_track（通常是 Kick）。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source_track": {
                "type": "string",
                "description": "触发侧链的轨道名，如 '01_DRUMS'",
            },
            "target_track": {
                "type": "string",
                "description": "被压缩的轨道名，如 '02_BASS'",
            },
        },
        "required": ["source_track", "target_track"],
    },
}

ALL_SCHEMAS = [
    PLAN_SONG_SCHEMA,
    GENERATE_MUSIC_SCHEMA,
    RENDER_AUDIO_SCHEMA,
    RECALL_MEMORY_SCHEMA,
    UPDATE_MEMORY_SCHEMA,
    ASK_KNOWLEDGE_SCHEMA,
    REGENERATE_TRACK_SCHEMA,
    SETUP_ABLETON_TEMPLATE_SCHEMA,
    IMPORT_STEMS_TO_ABLETON_SCHEMA,
    APPLY_SIDECHAIN_SCHEMA,
]

# ── tool implementations ───────────────────────────────────────────────────────

def execute_plan_song(inputs: dict, memory_store: dict) -> dict:
    """
    Pure logic — Claude does the planning; this function validates and
    normalises the blueprint that Claude already decided to create.

    In practice Claude calls plan_song and *provides* the blueprint in its
    tool response.  We just validate fields and return it back so the next
    tool call (generate_music) can use it.
    """
    desc = inputs.get("description", "")
    hints = inputs.get("style_hints", {}) or {}

    # Merge hints with passed description into a structured blueprint.
    # Claude will have already reasoned about this; we just build defaults
    # if somehow called directly.
    bpm = hints.get("preferred_bpm", 128)
    key = hints.get("preferred_key", "C_MAJOR")
    if key not in VALID_KEYS:
        key = "C_MAJOR"

    blueprint = {
        "bpm": bpm,
        "key": key,
        "description": desc,
        "segments": [
            {"name": "Intro",  "struct": "INTRO",  "bars": 8,  "e_level": 3, "tracks": ["DRUMS","BASS","CHORD"]},
            {"name": "Verse",  "struct": "VERSE",  "bars": 16, "e_level": 4, "tracks": ["DRUMS","BASS","CHORD","MELODY"]},
            {"name": "Build",  "struct": "BUILD",  "bars": 8,  "e_level": 6, "tracks": ["DRUMS","BASS","CHORD","MELODY"]},
            {"name": "Drop",   "struct": "DROP",   "bars": 16, "e_level": 8, "tracks": ["DRUMS","BASS","CHORD","MELODY"]},
            {"name": "Break",  "struct": "BREAK",  "bars": 8,  "e_level": 3, "tracks": ["BASS","CHORD","MELODY"]},
            {"name": "Outro",  "struct": "OUTRO",  "bars": 8,  "e_level": 2, "tracks": ["DRUMS","BASS","CHORD"]},
        ],
        "temperature": 0.85,
        "top_p": 0.92,
    }

    return {"status": "ok", "blueprint": blueprint}


_STRUCT_ALIASES = {
    "buildup": "BUILD", "build_up": "BUILD", "pre-drop": "BUILD", "predrop": "BUILD",
    "chorus": "DROP", "drop": "DROP",
    "intro": "INTRO", "introduction": "INTRO",
    "verse": "VERSE",
    "break": "BREAK", "breakdown": "BREAK",
    "outro": "OUTRO", "outro_": "OUTRO",
}
_VALID_STRUCTS = {"INTRO", "VERSE", "BUILD", "DROP", "BREAK", "OUTRO"}
_VALID_TRACKS  = {"DRUMS", "BASS", "CHORD", "MELODY"}

_NOTE_ALIASES = {
    "c#": "C#", "db": "C#", "d#": "D#", "eb": "D#", "f#": "F#", "gb": "F#",
    "g#": "G#", "ab": "G#", "a#": "A#", "bb": "A#",
    "c": "C", "d": "D", "e": "E", "f": "F", "g": "G", "a": "A", "b": "B",
}
_VALID_KEYS = {
    f"{n}_{s}"
    for n in ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    for s in ["MAJOR","MINOR"]
}

def _sanitize_key(key: str) -> str:
    if key in _VALID_KEYS:
        return key
    k = key.strip().replace(" ", "_").upper()
    if k in _VALID_KEYS:
        return k
    # Handle "Am", "Cmaj", "A minor", "C major" etc.
    k2 = k.lower().replace("maj", "major").replace("min", "minor").replace("_", " ")
    for suffix, mode in [("major", "MAJOR"), ("minor", "MINOR")]:
        if k2.endswith(suffix):
            note_raw = k2[:-len(suffix)].strip().rstrip("_").strip()
            note = _NOTE_ALIASES.get(note_raw.lower(), note_raw.upper())
            candidate = f"{note}_{mode}"
            if candidate in _VALID_KEYS:
                return candidate
    return "C_MAJOR"  # safe fallback

def _sanitize_segments(segments: list) -> list:
    clean = []
    for s in segments:
        struct = s.get("struct", "DROP")
        if struct not in _VALID_STRUCTS:
            struct = _STRUCT_ALIASES.get(struct.lower(), "DROP")
        tracks = [t.upper() for t in s.get("tracks", ["DRUMS","BASS","CHORD","MELODY"])]
        tracks = [t for t in tracks if t in _VALID_TRACKS] or ["DRUMS","BASS","CHORD","MELODY"]
        clean.append({
            "name":    s.get("name", struct),
            "struct":  struct,
            "bars":    max(1, min(64, int(s.get("bars", 16)))),
            "e_level": max(1, min(8,  int(s.get("e_level", 5)))),
            "tracks":  tracks,
        })
    return clean


def execute_generate_music(inputs: dict) -> dict:
    """Call PulseFormer /generate/song and save the MIDI locally."""
    blueprint = inputs["blueprint"]

    payload = {
        "bpm": blueprint["bpm"],
        "key": _sanitize_key(blueprint.get("key", "C_MAJOR")),
        "segments": _sanitize_segments(blueprint.get("segments", [])),
        "temperature": blueprint.get("temperature", 0.85),
        "top_p":       blueprint.get("top_p", 0.92),
        "max_new_tokens_per_segment": 600,
        "return_base64": True,
    }

    try:
        resp = httpx.post(
            f"{PULSEFORMER_API}/generate/song",
            json=payload,
            timeout=300.0,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return {"status": "error", "error": f"API {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

    data = resp.json()
    midi_b64 = data.get("midi_base64")
    if not midi_b64:
        return {"status": "error", "error": "API returned no midi_base64"}

    midi_bytes = base64.b64decode(midi_b64)
    file_id = str(uuid.uuid4())[:8]
    midi_path = MIDI_DIR / f"{file_id}.mid"
    midi_path.write_bytes(midi_bytes)

    return {
        "status": "ok",
        "midi_file_id": file_id,
        "midi_path": str(midi_path),
        "bpm": blueprint["bpm"],
        "key": blueprint["key"],
        "segments": [s["name"] for s in blueprint["segments"]],
    }


def execute_render_audio(inputs: dict) -> dict:
    """
    Convert MIDI → WAV via pretty_midi.fluidsynth() (Python binding, no CLI needed).
    Falls back to MIDI-only if synthesis fails.
    """
    file_id   = inputs["midi_file_id"]
    midi_path = MIDI_DIR / f"{file_id}.mid"

    if not midi_path.exists():
        return {"status": "error", "error": f"MIDI file not found: {file_id}"}

    wav_path = AUDIO_DIR / f"{file_id}.wav"

    # ── Render via pretty_midi (uses pyfluidsynth binding) ───────────────────
    try:
        import pretty_midi
        import scipy.io.wavfile as wavfile
        import numpy as np
        import concurrent.futures

        pm = pretty_midi.PrettyMIDI(str(midi_path))

        def _synth():
            return pm.fluidsynth(fs=44100)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_synth)
            try:
                audio_data = fut.result(timeout=30)
            except concurrent.futures.TimeoutError:
                raise RuntimeError("FluidSynth 渲染超时（>30s），跳过音频渲染")

        audio_int16 = np.int16(audio_data / np.max(np.abs(audio_data) + 1e-9) * 32767)
        wavfile.write(str(wav_path), 44100, audio_int16)
        audio_path = wav_path

        # Optional: WAV → MP3 via pydub
        try:
            from pydub import AudioSegment
            mp3_path = AUDIO_DIR / f"{file_id}.mp3"
            AudioSegment.from_wav(str(wav_path)).export(str(mp3_path), format="mp3")
            wav_path.unlink(missing_ok=True)
            audio_path = mp3_path
        except Exception:
            pass  # serve WAV if pydub unavailable

    except Exception as render_err:
        return {
            "status":        "ok",
            "audio_file_id": file_id,
            "audio_url":     None,
            "midi_url":      f"/midi/{file_id}",
            "note":          f"音频渲染失败（{render_err}），仅提供 MIDI 下载。",
        }

    suffix = audio_path.suffix  # .wav or .mp3
    return {
        "status":        "ok",
        "audio_file_id": file_id,
        "audio_path":    str(audio_path),
        "audio_url":     f"/audio/{file_id}{suffix}",
        "midi_url":      f"/midi/{file_id}",
    }


def execute_recall_memory(memory_store: dict) -> dict:
    if not memory_store:
        return {"status": "ok", "memory": {}, "summary": "暂无用户偏好记录。"}
    summary_parts = []
    for k, v in memory_store.items():
        summary_parts.append(f"{k}: {v}")
    return {
        "status": "ok",
        "memory": memory_store,
        "summary": "；".join(summary_parts),
    }


def execute_update_memory(inputs: dict, memory_store: dict) -> dict:
    key   = inputs["key"]
    value = inputs["value"]
    memory_store[key] = value
    return {"status": "ok", "updated": {key: value}}


def execute_ask_knowledge(inputs: dict) -> dict:
    """Query the RAG service for music production knowledge."""
    query = inputs["query"]
    top_k = inputs.get("top_k", 3)
    try:
        resp = httpx.post(
            f"{RAG_API}/chat",
            json={"query": query, "top_k": top_k, "use_rerank": False},
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "status": "ok",
            "answer": data.get("answer", ""),
            "sources": data.get("sources", []),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def execute_regenerate_track(inputs: dict) -> dict:
    """Lock all tracks except target and regenerate it via PulseFormer API."""
    file_id = inputs["midi_file_id"]
    midi_path = MIDI_DIR / f"{file_id}.mid"
    if not midi_path.exists():
        return {"status": "error", "error": f"MIDI file not found: {file_id}"}

    midi_b64 = base64.b64encode(midi_path.read_bytes()).decode()

    payload = {
        "bpm":                 inputs.get("bpm", 128),
        "key":                 inputs.get("key", "C_MAJOR"),
        "struct":              inputs.get("struct", "DROP"),
        "target_track":        inputs["target_track"],
        "locked_midi_base64":  midi_b64,
        "e_level":             inputs.get("e_level", 5),
        "bars":                inputs.get("bars", 16),
        "return_base64":       True,
    }

    try:
        resp = httpx.post(
            f"{PULSEFORMER_API}/tools/regenerate_track",
            json=payload,
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"status": "error", "error": str(e)}

    midi_bytes = base64.b64decode(data["midi_base64"])
    new_id = str(uuid.uuid4())[:8]
    new_path = MIDI_DIR / f"{new_id}.mid"
    new_path.write_bytes(midi_bytes)

    return {
        "status": "ok",
        "midi_file_id": new_id,
        "regenerated_track": inputs["target_track"],
        "original_file_id": file_id,
    }


def execute_setup_ableton_template(inputs: dict) -> dict:
    """Create EDM template in Ableton via ableton-mcp bridge."""
    bpm = inputs.get("bpm", 128)
    key = inputs.get("key", "C_MAJOR")
    try:
        resp = httpx.post(
            f"{ABLETON_API}/setup_edm_template",
            json={"bpm": bpm, "key": key},
            timeout=30.0,
        )
        resp.raise_for_status()
        return {"status": "ok", **resp.json()}
    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "无法连接 Ableton MCP Bridge（localhost:8002）。请确认 Ableton Live 已运行且 ableton-mcp Remote Script 已加载。",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def execute_import_stems_to_ableton(inputs: dict) -> dict:
    """Import PulseFormer MIDI stems into Ableton tracks."""
    file_id   = inputs["midi_file_id"]
    view_mode = inputs.get("view_mode", "arrange")
    midi_path = MIDI_DIR / f"{file_id}.mid"

    if not midi_path.exists():
        return {"status": "error", "error": f"MIDI file not found: {file_id}"}

    midi_b64 = base64.b64encode(midi_path.read_bytes()).decode()
    key = inputs.get("key", "C_MINOR")
    try:
        resp = httpx.post(
            f"{ABLETON_API}/import_stems",
            json={"midi_base64": midi_b64, "view_mode": view_mode, "key": key},
            timeout=60.0,
        )
        resp.raise_for_status()
        return {"status": "ok", **resp.json()}
    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "无法连接 Ableton MCP Bridge。请确认 Ableton Live 已运行。",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def execute_llm_edit_ableton(inputs: dict) -> dict:
    """Call /llm_edit: LLM interprets instruction → ops → re-inject into Ableton."""
    try:
        resp = httpx.post(
            f"{ABLETON_API}/llm_edit",
            json={
                "track_name":  inputs.get("track_name", "all"),
                "instruction": inputs["instruction"],
                "seed":        inputs.get("seed", 0),
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        return {"status": "ok", **resp.json()}
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = e.response.json().get("detail", "")
        except Exception:
            pass
        return {"status": "error", "error": detail or str(e)}
    except httpx.ConnectError:
        return {"status": "error", "error": "无法连接 Ableton Bridge（localhost:8002）"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def execute_apply_sidechain(inputs: dict) -> dict:
    """Configure sidechain compression in Ableton."""
    try:
        resp = httpx.post(
            f"{ABLETON_API}/apply_sidechain",
            json={"source_track": inputs["source_track"],
                  "target_track": inputs["target_track"]},
            timeout=30.0,
        )
        resp.raise_for_status()
        return {"status": "ok", **resp.json()}
    except httpx.ConnectError:
        return {
            "status": "error",
            "error": "无法连接 Ableton MCP Bridge。请确认 Ableton Live 已运行。",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ── dispatcher ─────────────────────────────────────────────────────────────────

def dispatch_tool(tool_name: str, tool_input: dict, memory_store: dict) -> Any:
    """
    Called by agent.py for each tool_use block Claude returns.
    Returns a JSON-serialisable result dict.
    """
    try:
        if tool_name == "plan_song":
            return execute_plan_song(tool_input, memory_store)
        elif tool_name == "generate_music":
            return execute_generate_music(tool_input)
        elif tool_name == "render_audio":
            return execute_render_audio(tool_input)
        elif tool_name == "recall_memory":
            return execute_recall_memory(memory_store)
        elif tool_name == "update_memory":
            return execute_update_memory(tool_input, memory_store)
        elif tool_name == "ask_knowledge":
            return execute_ask_knowledge(tool_input)
        elif tool_name == "regenerate_track":
            return execute_regenerate_track(tool_input)
        elif tool_name == "setup_ableton_template":
            return execute_setup_ableton_template(tool_input)
        elif tool_name == "import_stems_to_ableton":
            return execute_import_stems_to_ableton(tool_input)
        elif tool_name == "apply_sidechain":
            return execute_apply_sidechain(tool_input)
        else:
            return {"status": "error", "error": f"Unknown tool: {tool_name}"}
    except Exception:
        return {"status": "error", "error": traceback.format_exc()}


# ── helpers ────────────────────────────────────────────────────────────────────

def _find_soundfont() -> str | None:
    """Search common locations for a .sf2 soundfont file."""
    candidates = [
        Path("C:/soundfonts/default.sf2"),
        Path("C:/Windows/System32/drivers/gm.dls"),
        Path("/usr/share/sounds/sf2/FluidR3_GM.sf2"),
        Path("/usr/share/sounds/sf2/TimGM6mb.sf2"),
        Path("/usr/share/soundfonts/default.sf2"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None
