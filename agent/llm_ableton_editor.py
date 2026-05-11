"""
agent/llm_ableton_editor.py
============================
LLM-driven MIDI note editor that modifies Ableton clips via structured operations.

Flow:
  notes (beats) + user instruction
    → LLM outputs JSON operation list
    → apply_ops() transforms notes
    → caller re-injects into Ableton via add_notes_to_arrangement_clip / add_notes_to_clip
"""

from __future__ import annotations

import json
import os
import random
import re
from typing import Any

from openai import OpenAI

# ── LLM client (same Ollama endpoint as workflow.py) ─────────────────────────

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL    = os.environ.get("OLLAMA_MODEL",    "qwen2.5:7b-instruct-q4_K_M")

_client = OpenAI(base_url=OLLAMA_BASE_URL, api_key="ollama")

# ── Drum GM note names ────────────────────────────────────────────────────────

_DRUM_NAMES: dict[int, str] = {
    35: "Kick2", 36: "Kick", 37: "Rim", 38: "Snare", 39: "Clap",
    40: "ESnare", 41: "LowTom3", 42: "ClosedHH", 43: "LowTom2",
    44: "FootHH", 45: "LowTom", 46: "OpenHH", 47: "MidTom2",
    48: "MidTom", 49: "Crash", 50: "HiTom", 51: "Ride",
    52: "ChinaCym", 53: "RideBell", 55: "Splash", 57: "Crash2",
    59: "Ride2",
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _pitch_label(pitch: int, is_drum: bool = False) -> str:
    if is_drum:
        return _DRUM_NAMES.get(pitch, f"D{pitch}")
    return f"{_NOTE_NAMES[pitch % 12]}{pitch // 12 - 1}"


# ── Notes → compact text for LLM ─────────────────────────────────────────────

def notes_to_text(notes: list[dict], is_drum: bool = False, max_notes: int = 80) -> str:
    if not notes:
        return "(no notes)"

    sorted_notes = sorted(notes, key=lambda n: n["start_time"])

    # Group by bar (4 beats = 1 bar)
    bars: dict[int, list[dict]] = {}
    for n in sorted_notes:
        bar = int(n["start_time"] // 4)
        bars.setdefault(bar, []).append(n)

    shown = 0
    lines: list[str] = [f"[{len(notes)} notes, {max(bars) + 1} bars]"]

    for bar_idx in sorted(bars.keys()):
        bar_notes = bars[bar_idx]
        lines.append(f"Bar {bar_idx + 1}:")
        for n in sorted(bar_notes, key=lambda x: x["start_time"]):
            if shown >= max_notes:
                remaining = sum(len(b) for b in bars.values()) - shown
                lines.append(f"  ... (+{remaining} more notes)")
                return "\n".join(lines)
            beat_in_bar = n["start_time"] - bar_idx * 4
            label = _pitch_label(n["pitch"], is_drum)
            lines.append(
                f"  b{beat_in_bar:.2f} {label:8s} vel={n['velocity']:3d}  dur={n['duration']:.2f}"
            )
            shown += 1

    return "\n".join(lines)


# ── System prompt + operation schema ─────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are an expert EDM music editor. You modify MIDI note data to match the user's instruction.
Output ONLY a JSON array of operations. Do not explain. No markdown.

Available operations:
{"op":"transpose",       "semitones":<int>}
  Shift every pitch N semitones (+ = up, - = down). Clamps to [0,127].

{"op":"velocity_scale",  "factor":<float>, "min":<0-127>, "max":<0-127>}
  Multiply velocity by factor, clamp to min/max range.

{"op":"set_velocity",    "value":<0-127>}
  Set all velocities to a fixed value.

{"op":"quantize",        "grid":<beats>, "strength":<0.0-1.0>}
  Snap note start_times toward grid. grid=0.25 → 16th note grid. strength=1.0 → hard snap.

{"op":"humanize",        "timing":<beats>, "velocity":<int>}
  Add small random variation. Typical: timing=0.04, velocity=8.

{"op":"time_stretch",    "factor":<float>}
  Scale all start_times and durations (0.5=half speed, 2.0=double speed).

{"op":"thin",            "keep_every":<int>}
  Keep every N-th note (ordered by start_time). E.g. keep_every=2 removes half the notes.

{"op":"filter_pitch",    "min":<0-127>, "max":<0-127>}
  Remove notes whose pitch is outside [min, max].

{"op":"filter_velocity", "min":<0-127>, "max":<0-127>}
  Remove notes whose velocity is outside [min, max].

{"op":"delete_range",    "beat_start":<float>, "beat_end":<float>}
  Delete all notes that start within [beat_start, beat_end).

{"op":"reverse"}
  Mirror note positions: last note becomes first. Keeps total clip length.

{"op":"octave_shift",    "octave":<int>}
  Shift pitch by 12*octave semitones. E.g. octave=-1 = one octave down.

{"op":"fill_drums_pattern", "bar_start":<int>, "bar_end":<int>, "style":<str>}
  Fill an EMPTY bar range with a generated drum pattern.
  bar_start and bar_end are 1-indexed (e.g. bar_start=39, bar_end=49).
  style options: "four_on_floor" | "minimal" | "tech_house" | "breakbeat"
  Use this when the user says a section is empty/blank and needs drums added.

{"op":"add_notes", "notes":[{"pitch":<0-127>,"start_time":<beats>,"duration":<beats>,"velocity":<0-127>}, ...]}
  Insert specific MIDI notes (merged with existing, not replacing).
  Beats are absolute from clip start. 1 bar = 4 beats.

Always return: {"ops": [ ...list of operations... ]}
Example for "make it quieter with swing":
{"ops":[{"op":"velocity_scale","factor":0.75,"min":30,"max":110},{"op":"humanize","timing":0.04,"velocity":5}]}
Example for "bar 5-8 is empty, add drums":
{"ops":[{"op":"fill_drums_pattern","bar_start":5,"bar_end":8,"style":"four_on_floor"}]}
"""


def _build_user_prompt(
    track_name: str, bpm: float, key: str, notes: list[dict], instruction: str, is_drum: bool
) -> str:
    notes_text = notes_to_text(notes, is_drum=is_drum)
    return (
        f"Track: {track_name}  BPM: {bpm}  Key: {key}\n\n"
        f"Current notes:\n{notes_text}\n\n"
        f"Instruction: {instruction}"
    )


# ── LLM call ─────────────────────────────────────────────────────────────────

def ask_llm_for_ops(
    track_name: str,
    notes: list[dict],
    instruction: str,
    bpm: float = 128.0,
    key: str = "C_MINOR",
    is_drum: bool = False,
) -> tuple[list[dict], str]:
    """
    Call Ollama to get a list of operations for the given instruction.
    Returns (ops_list, raw_llm_response).
    """
    user_msg = _build_user_prompt(track_name, bpm, key, notes, instruction, is_drum)

    resp = _client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        response_format={"type": "json_object"},
        max_tokens=512,
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()

    # Parse: model may return {"ops":[...]}, [...], or a single {"op":...}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            ops = parsed
        elif isinstance(parsed, dict):
            if "op" in parsed:
                # Single operation object — wrap in list
                ops = [parsed]
            else:
                # Try common wrapper keys
                ops = []
                for key_name in ("ops", "operations", "result", "changes", "edits"):
                    if isinstance(parsed.get(key_name), list):
                        ops = parsed[key_name]
                        break
                if not ops:
                    # Take the first list value found
                    ops = next((v for v in parsed.values() if isinstance(v, list)), [])
        else:
            ops = []
    except json.JSONDecodeError:
        ops = []

    return ops, raw


# ── Operation executor ────────────────────────────────────────────────────────

def apply_ops(notes: list[dict], ops: list[dict], seed: int = 0) -> list[dict]:
    """Apply a sequence of operations to a notes list. Returns new notes list."""
    rng = random.Random(seed)
    result = [dict(n) for n in notes]

    for op_def in ops:
        op = op_def.get("op", "")

        if op == "transpose":
            delta = int(op_def.get("semitones", 0))
            for n in result:
                n["pitch"] = max(0, min(127, n["pitch"] + delta))

        elif op == "octave_shift":
            delta = int(op_def.get("octave", 0)) * 12
            for n in result:
                n["pitch"] = max(0, min(127, n["pitch"] + delta))

        elif op == "velocity_scale":
            factor = float(op_def.get("factor", 1.0))
            vmin   = int(op_def.get("min", 1))
            vmax   = int(op_def.get("max", 127))
            for n in result:
                n["velocity"] = max(vmin, min(vmax, int(round(n["velocity"] * factor))))

        elif op == "set_velocity":
            val = max(1, min(127, int(op_def.get("value", 90))))
            for n in result:
                n["velocity"] = val

        elif op == "quantize":
            grid     = float(op_def.get("grid", 0.25))
            strength = float(op_def.get("strength", 1.0))
            for n in result:
                snapped = round(n["start_time"] / grid) * grid
                n["start_time"] = round(
                    n["start_time"] + (snapped - n["start_time"]) * strength, 4
                )

        elif op == "humanize":
            t_jitter = float(op_def.get("timing", 0.04))
            v_jitter = int(op_def.get("velocity", 8))
            for n in result:
                n["start_time"] = round(
                    max(0.0, n["start_time"] + rng.uniform(-t_jitter, t_jitter)), 4
                )
                n["velocity"] = max(1, min(127,
                    n["velocity"] + rng.randint(-v_jitter, v_jitter)
                ))

        elif op == "time_stretch":
            factor = float(op_def.get("factor", 1.0))
            for n in result:
                n["start_time"] = round(n["start_time"] * factor, 4)
                n["duration"]   = round(n["duration"]   * factor, 4)

        elif op == "thin":
            every = max(1, int(op_def.get("keep_every", 2)))
            sorted_r = sorted(result, key=lambda x: x["start_time"])
            result = [n for i, n in enumerate(sorted_r) if i % every == 0]

        elif op == "filter_pitch":
            pmin = int(op_def.get("min", 0))
            pmax = int(op_def.get("max", 127))
            result = [n for n in result if pmin <= n["pitch"] <= pmax]

        elif op == "filter_velocity":
            vmin = int(op_def.get("min", 0))
            vmax = int(op_def.get("max", 127))
            result = [n for n in result if vmin <= n["velocity"] <= vmax]

        elif op == "delete_range":
            bs = float(op_def.get("beat_start", 0.0))
            be = float(op_def.get("beat_end", 0.0))
            result = [n for n in result if not (bs <= n["start_time"] < be)]

        elif op == "reverse":
            if result:
                end = max(n["start_time"] + n["duration"] for n in result)
                result = [
                    {**n, "start_time": round(end - n["start_time"] - n["duration"], 4)}
                    for n in result
                ]
                result.sort(key=lambda x: x["start_time"])

        elif op == "add_notes":
            new_notes = op_def.get("notes", [])
            for n in new_notes:
                result.append({
                    "pitch":      max(0, min(127, int(n.get("pitch", 60)))),
                    "start_time": round(float(n.get("start_time", 0.0)), 4),
                    "duration":   round(max(0.0625, float(n.get("duration", 0.25))), 4),
                    "velocity":   max(1, min(127, int(n.get("velocity", 90)))),
                })
            result.sort(key=lambda x: x["start_time"])

        elif op == "fill_drums_pattern":
            bar_start = int(op_def.get("bar_start", 1))
            bar_end   = int(op_def.get("bar_end",   bar_start + 1))
            style     = op_def.get("style", "four_on_floor")
            new_notes = _generate_drum_pattern(bar_start, bar_end, style, rng)
            result.extend(new_notes)
            result.sort(key=lambda x: x["start_time"])

        elif op == "fill_chord_loop":
            if not result:
                pass  # no notes to loop
            else:
                BEATS_PER_BAR = 4.0
                # Find the total length (from last note end)
                total_end = max(n["start_time"] + n["duration"] for n in result)
                total_bars = max(1, int((total_end + BEATS_PER_BAR - 1) // BEATS_PER_BAR))

                # Use first 4 bars as pattern source (or fewer if song is short)
                pattern_bars = min(4, total_bars)
                pattern_end  = pattern_bars * BEATS_PER_BAR
                pattern_notes = [n for n in result if n["start_time"] < pattern_end]

                if pattern_notes:
                    filled: list[dict] = list(result)
                    existing_starts = {round(n["start_time"], 2) for n in result}
                    for bar in range(pattern_bars, total_bars, pattern_bars):
                        offset = bar * BEATS_PER_BAR
                        for n in pattern_notes:
                            new_start = round(n["start_time"] + offset, 4)
                            if round(new_start, 2) not in existing_starts:
                                filled.append({
                                    "pitch":      n["pitch"],
                                    "start_time": new_start,
                                    "duration":   n["duration"],
                                    "velocity":   n["velocity"],
                                })
                                existing_starts.add(round(new_start, 2))
                    result = sorted(filled, key=lambda x: x["start_time"])

    return result


# ── Drum pattern generator ────────────────────────────────────────────────────

# GM drum pitches
_KICK  = 36
_SNARE = 38
_CLAP  = 39
_HHCL  = 42   # closed hi-hat
_HHOP  = 46   # open hi-hat
_CRASH = 49
_RIDE  = 51


def _generate_drum_pattern(
    bar_start: int,
    bar_end: int,
    style: str,
    rng: random.Random,
) -> list[dict]:
    """
    Generate drum notes for bars [bar_start, bar_end) (1-indexed, 4 beats per bar).
    Returns notes with start_time in beats.
    """
    notes: list[dict] = []
    BEATS_PER_BAR = 4
    beat_offset = (bar_start - 1) * BEATS_PER_BAR
    n_bars = bar_end - bar_start

    def note(pitch: int, beat: float, dur: float = 0.2, vel: int = 100) -> dict:
        return {
            "pitch":      pitch,
            "start_time": round(beat_offset + beat, 4),
            "duration":   dur,
            "velocity":   max(1, min(127, vel + rng.randint(-5, 5))),
        }

    for bar in range(n_bars):
        b = bar * BEATS_PER_BAR   # beat within pattern

        if style == "four_on_floor":
            # Kick on every beat
            for beat in [0, 1, 2, 3]:
                notes.append(note(_KICK, b + beat, vel=100))
            # Snare/clap on 2 and 4
            notes.append(note(_SNARE, b + 1, vel=90))
            notes.append(note(_SNARE, b + 3, vel=90))
            # Closed HH every 8th note
            for hh in [x * 0.5 for x in range(8)]:
                vel = 80 if hh % 1.0 == 0 else 65
                notes.append(note(_HHCL, b + hh, vel=vel))

        elif style == "minimal":
            # Kick on 1 and 3
            notes.append(note(_KICK, b + 0, vel=105))
            notes.append(note(_KICK, b + 2, vel=100))
            # Snare on 2 and 4
            notes.append(note(_SNARE, b + 1, vel=88))
            notes.append(note(_SNARE, b + 3, vel=88))
            # Sparse HH on every beat
            for beat in [0, 1, 2, 3]:
                notes.append(note(_HHCL, b + beat, vel=70))

        elif style == "tech_house":
            # Kick on every beat (house style)
            for beat in [0, 1, 2, 3]:
                notes.append(note(_KICK, b + beat, vel=105))
            # Clap on 2 and 4
            notes.append(note(_CLAP, b + 1, vel=85))
            notes.append(note(_CLAP, b + 3, vel=85))
            # Open HH on offbeats (0.5, 1.5, 2.5, 3.5)
            for hh in [0.5, 1.5, 2.5, 3.5]:
                notes.append(note(_HHOP, b + hh, vel=75))
            # Closed HH on the beat
            for beat in [0, 1, 2, 3]:
                notes.append(note(_HHCL, b + beat, vel=60))

        elif style == "breakbeat":
            # Kick on 1 and 2.5
            notes.append(note(_KICK, b + 0,   vel=110))
            notes.append(note(_KICK, b + 2.5, vel=95))
            # Snare on 2 and syncopated 3.5
            notes.append(note(_SNARE, b + 1,   vel=95))
            notes.append(note(_SNARE, b + 3.5, vel=80))
            # 16th HH with accents
            for i, hh in enumerate([x * 0.25 for x in range(16)]):
                vel = 85 if i % 4 == 0 else 55
                notes.append(note(_HHCL, b + hh, vel=vel))

        else:  # fallback = four_on_floor
            for beat in [0, 1, 2, 3]:
                notes.append(note(_KICK, b + beat, vel=100))
            notes.append(note(_SNARE, b + 1, vel=90))
            notes.append(note(_SNARE, b + 3, vel=90))

    return notes


# ── Chat-style multi-track edit ───────────────────────────────────────────────

_CHAT_SYSTEM_PROMPT = """\
You are an expert EDM producer inside Ableton Live. The user gives instructions in any language.
Return ONLY this JSON — no explanation, no markdown, no extra keys:
{"edits":[{"track":"<TRACK_NAME>","ops":[<OP>, ...]}, ...]}

CRITICAL RULES:
- You MUST only use operations from the vocabulary below. Do NOT invent new formats.
- Do NOT generate raw note data unless using "add_notes" op exactly as specified.
- When user mentions empty/blank/空白 bars, ALWAYS use "fill_drums_pattern".

OPERATION VOCABULARY (copy op names exactly):
{"op":"fill_drums_pattern","bar_start":<int>,"bar_end":<int>,"style":<str>}
  USE THIS when user says bars are empty/blank/空白/没有. Generates drum pattern.
  bar_start/bar_end: 1-indexed bar numbers. style: "four_on_floor","minimal","tech_house","breakbeat"
{"op":"add_notes","notes":[{"pitch":<0-127>,"start_time":<beats>,"duration":<beats>,"velocity":<0-127>},...]}
  Add specific notes. start_time in beats from clip start. Bar N = beat (N-1)*4.
{"op":"transpose","semitones":<int>}
{"op":"octave_shift","octave":<int>}
{"op":"velocity_scale","factor":<float>,"min":<0-127>,"max":<0-127>}
{"op":"set_velocity","value":<0-127>}
{"op":"quantize","grid":<beats>,"strength":<0.0-1.0>}
{"op":"humanize","timing":<beats>,"velocity":<int>}
{"op":"thin","keep_every":<int>}
{"op":"delete_range","beat_start":<float>,"beat_end":<float>}
{"op":"reverse"}

FEW-SHOT EXAMPLES:
User: "39-49小节出现完全空白 帮我加入鼓组的pattern完善"
Output: {"edits":[{"track":"TOMI-DRUMS","ops":[{"op":"fill_drums_pattern","bar_start":39,"bar_end":49,"style":"four_on_floor"}]}]}

User: "bars 5 to 8 are empty, add minimal drums"
Output: {"edits":[{"track":"TOMI-DRUMS","ops":[{"op":"fill_drums_pattern","bar_start":5,"bar_end":8,"style":"minimal"}]}]}

User: "让旋律更稀疏，鼓加点人性化"
Output: {"edits":[{"track":"TOMI-MELODY","ops":[{"op":"thin","keep_every":2}]},{"track":"TOMI-DRUMS","ops":[{"op":"humanize","timing":0.04,"velocity":8}]}]}

User: "整体音量调小，bass下移八度"
Output: {"edits":[{"track":"TOMI-DRUMS","ops":[{"op":"velocity_scale","factor":0.8,"min":30,"max":127}]},{"track":"TOMI-BASS","ops":[{"op":"octave_shift","octave":-1},{"op":"velocity_scale","factor":0.8,"min":30,"max":127}]},{"track":"TOMI-MELODY","ops":[{"op":"velocity_scale","factor":0.8,"min":30,"max":127}]}]}
"""


def _build_chat_prompt(track_states: dict[str, dict], instruction: str) -> str:
    """
    track_states: {track_name: {"notes": list, "bpm": float, "key": str, "is_drum": bool}}
    """
    lines = [f"Instruction: {instruction}\n", "Current tracks:"]
    for tname, info in track_states.items():
        notes = info["notes"]
        bpm   = info.get("bpm", 128)
        is_drum = info.get("is_drum", False)
        lines.append(f"\n--- {tname} (BPM={bpm}, key={info.get('key','?')}) ---")
        lines.append(notes_to_text(notes, is_drum=is_drum, max_notes=40))
    return "\n".join(lines)


_EMPTY_DRUM_PATTERNS = [
    # Chinese: "39-49小节空白/没有/加入" style
    r"(\d+)\s*[-–~～至到]\s*(\d+)\s*小节.*?(?:空白|没有|缺少|加入|填充|补充|加鼓|加drum)",
    r"(?:空白|没有|缺少).*?(\d+)\s*[-–~～至到]\s*(\d+)\s*小节",
    # English: "bars 5-8 empty/blank/add drums"
    r"bars?\s+(\d+)\s*[-–to]+\s*(\d+).*?(?:empty|blank|missing|add drum|fill drum)",
    r"(?:empty|blank|no notes?).*?bars?\s+(\d+)\s*[-–to]+\s*(\d+)",
]

_DRUM_STYLE_MAP = {
    "minimal": "minimal", "极简": "minimal", "简单": "minimal",
    "tech_house": "tech_house", "tech house": "tech_house", "科技浩室": "tech_house",
    "breakbeat": "breakbeat", "断拍": "breakbeat",
    "four_on_floor": "four_on_floor",
}


def _detect_fill_drums(instruction: str, track_states: dict[str, dict]) -> list[dict] | None:
    """
    Rule-based detector for 'fill empty bars with drums' instructions.
    Returns list of edits if detected, else None.
    """
    instr_lower = instruction.lower()
    bar_start = bar_end = None

    for pat in _EMPTY_DRUM_PATTERNS:
        m = re.search(pat, instruction, re.IGNORECASE)
        if m:
            bar_start, bar_end = int(m.group(1)), int(m.group(2))
            if bar_start > bar_end:
                bar_start, bar_end = bar_end, bar_start
            break

    if bar_start is None:
        return None

    # Infer style from instruction keywords
    style = "four_on_floor"
    for kw, s in _DRUM_STYLE_MAP.items():
        if kw in instr_lower:
            style = s
            break

    # Find drum track name
    drum_track = next(
        (t for t in track_states if "DRUM" in t.upper()),
        next(iter(track_states), "TOMI-DRUMS"),
    )

    return [{"track": drum_track, "ops": [
        {"op": "fill_drums_pattern", "bar_start": bar_start, "bar_end": bar_end, "style": style}
    ]}]


_CHORD_FILL_PATTERNS = [
    r"chord.*(?:太少|稀疏|空|不够|填满|填充|更密|加密|补全|铺满|fill|sparse|empty|thin)",
    r"(?:填满|填充|铺满|加密|让.*更密).*chord",
    r"chord.*(?:whole song|整首|全曲|全部)",
    r"(?:whole song|整首|全曲|全部).*chord",
]

def _detect_chord_fill(instruction: str, track_states: dict[str, dict]) -> list[dict] | None:
    instr_lower = instruction.lower()
    matched = any(re.search(p, instr_lower, re.IGNORECASE) for p in _CHORD_FILL_PATTERNS)
    if not matched:
        return None
    chord_track = next(
        (t for t in track_states if "CHORD" in t.upper()),
        next(iter(track_states), "TOMI-CHORD"),
    )
    return [{"track": chord_track, "ops": [{"op": "fill_chord_loop"}]}]


def ask_llm_chat_edit(
    track_states: dict[str, dict],
    instruction: str,
) -> tuple[list[dict], str]:
    """
    Single LLM call that decides WHICH tracks to edit and WHAT operations to apply.
    Rule-based detector runs first for fill_drums_pattern instructions.

    Returns:
        edits  — list of {"track": str, "ops": list}
        raw    — raw LLM response string
    """
    # Rule-based shortcuts (bypasses LLM for reliable detection)
    rule_edits = _detect_fill_drums(instruction, track_states)
    if rule_edits is not None:
        return rule_edits, "[rule-based] fill_drums_pattern detected"
    rule_edits = _detect_chord_fill(instruction, track_states)
    if rule_edits is not None:
        return rule_edits, "[rule-based] fill_chord_loop detected"

    user_msg = _build_chat_prompt(track_states, instruction)

    resp = _client.chat.completions.create(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": _CHAT_SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        response_format={"type": "json_object"},
        max_tokens=800,
        temperature=0.2,
    )
    raw = (resp.choices[0].message.content or "").strip()

    try:
        parsed = json.loads(raw)
        edits = parsed.get("edits", [])
        # Tolerate flat single-track: {"track":..., "ops":[...]}
        if not edits and "track" in parsed and "ops" in parsed:
            edits = [parsed]
    except (json.JSONDecodeError, AttributeError):
        edits = []

    return edits, raw
