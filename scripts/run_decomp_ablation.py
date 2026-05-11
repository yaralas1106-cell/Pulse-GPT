"""
run_decomp_ablation.py
======================
Generate 128-bar MIDI for all 5 pipeline decomposition ablation conditions,
then evaluate with eval/clean_ablation_eval.py and print a paste-ready LaTeX table.

Usage:
    # Generate all conditions (requires m_film_v6_best.pt):
    python scripts/run_decomp_ablation.py --step generate --out_dir output/decomp_ablation

    # Evaluate already-generated MIDI:
    python scripts/run_decomp_ablation.py --step eval --out_dir output/decomp_ablation

    # Full pipeline (generate + eval):
    python scripts/run_decomp_ablation.py --step all --out_dir output/decomp_ablation

Condition directory layout inside out_dir/:
    full_pf/          P1.mid ... P8.mid
    wo_film/          P1.mid ... P8.mid
    wo_scheduler/     P1.mid ... P8.mid
    wo_density_mask/  P1.mid ... P8.mid
    wo_daw_postproc/  P1.mid ... P8.mid
"""

import argparse
import os
import sys
import subprocess
from collections import defaultdict

# ── 8 evaluation prompts ─────────────────────────────────────────────────────
# Each prompt defines a full 128-bar song blueprint (8 sections × 16 bars).
# Genres/keys/BPMs are varied to match the diversity of the MOS study stimuli.
#
# Blueprint section E_levels follow a canonical EDM arc:
#   Intro(3) → Verse(5) → Build(8) → Drop(9) → Break(4) → Build2(7) → Drop2(9) → Outro(2)
# For w/o Scheduler, ALL sections use constant E=5.

SONG_BLUEPRINTS = [
    # P1 — House / A minor / 128 BPM
    {
        "id": "P1",
        "bpm": 128.0,
        "sections": [
            {"name": "Intro",   "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Verse",   "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Build",   "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Drop",    "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",   "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Break",   "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Build2",  "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Drop2",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",   "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
            {"name": "Outro",   "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO",  "genre": "GENRE_HOUSE", "key": "KEY_A_MINOR"},
        ],
    },
    # P2 — House / F minor / 126 BPM
    {
        "id": "P2", "bpm": 126.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_HOUSE", "key": "KEY_F_MINOR"},
        ],
    },
    # P3 — Techno / C minor / 138 BPM
    {
        "id": "P3", "bpm": 138.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_TECHNO", "key": "KEY_C_MINOR"},
        ],
    },
    # P4 — Techno / G minor / 140 BPM
    {
        "id": "P4", "bpm": 140.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_TECHNO", "key": "KEY_G_MINOR"},
        ],
    },
    # P5 — Trance / D minor / 138 BPM
    {
        "id": "P5", "bpm": 138.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_TRANCE", "key": "KEY_D_MINOR"},
        ],
    },
    # P6 — Trance / E minor / 136 BPM
    {
        "id": "P6", "bpm": 136.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_TRANCE", "key": "KEY_E_MINOR"},
        ],
    },
    # P7 — D&B / B minor / 174 BPM
    {
        "id": "P7", "bpm": 174.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 3, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Verse",  "bars": 16, "e_level": 5, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Build",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Drop",   "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Break",  "bars": 16, "e_level": 4, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Build2", "bars": 16, "e_level": 7, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 9, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_DRUMS", "HAS_BASS"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_DRUM_AND_BASS", "key": "KEY_B_MINOR"},
        ],
    },
    # P8 — Ambient / C major / 90 BPM
    {
        "id": "P8", "bpm": 90.0,
        "sections": [
            {"name": "Intro",  "bars": 16, "e_level": 2, "tracks": ["HAS_CHORD"],
             "struct": "STRUCT_INTRO", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Verse",  "bars": 16, "e_level": 4, "tracks": ["HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_VERSE", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Build",  "bars": 16, "e_level": 6, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Drop",   "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Break",  "bars": 16, "e_level": 3, "tracks": ["HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BREAK", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Build2", "bars": 16, "e_level": 6, "tracks": ["HAS_DRUMS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_BUILD", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Drop2",  "bars": 16, "e_level": 8, "tracks": ["HAS_DRUMS", "HAS_BASS", "HAS_CHORD", "HAS_MELODY"],
             "struct": "STRUCT_DROP",  "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
            {"name": "Outro",  "bars": 16, "e_level": 2, "tracks": ["HAS_CHORD"],
             "struct": "STRUCT_OUTRO", "genre": "GENRE_AMBIENT", "key": "KEY_C_MAJOR"},
        ],
    },
]

# ── ablation conditions ───────────────────────────────────────────────────────

CONDITIONS = {
    "full_pf":         {"use_film": True,  "use_scheduler": True,  "use_density_mask": True,  "use_daw_postproc": True},
    "wo_film":         {"use_film": False, "use_scheduler": True,  "use_density_mask": True,  "use_daw_postproc": True},
    "wo_scheduler":    {"use_film": True,  "use_scheduler": False, "use_density_mask": True,  "use_daw_postproc": True},
    "wo_density_mask": {"use_film": True,  "use_scheduler": True,  "use_density_mask": False, "use_daw_postproc": True},
    "wo_daw_postproc": {"use_film": True,  "use_scheduler": True,  "use_density_mask": True,  "use_daw_postproc": False},
}

FILM_CKPT   = "dataset/processed/m_film_v6_best.pt"
CP_CKPT     = "dataset/processed/m_cp_v6_best.pt"   # v6 vocab (234 pitches)
VOCAB_PATH  = "dataset/processed/pulse_cp_vocab_5d_v6.json"


# ── helper: build prompt tokens for one section ───────────────────────────────

def make_prompt(section: dict, bpm: float, use_scheduler: bool, use_film: bool) -> list:
    prompt = [f"[{section['genre']}]", f"[{section['struct']}]"]
    for t in section["tracks"]:
        prompt.append(f"[{t}]")
    prompt.append(f"[{section['key']}]")
    prompt.append(f"[BPM_{int(bpm)}]")
    if not use_film:
        # CP-Transformer uses token-level energy; FiLM conditions externally
        e = section["e_level"] if use_scheduler else 5
        prompt.append(f"[ENERGY_LEVEL_{e}]")
    prompt.append("[BAR_START]")
    return prompt


# ── generation ────────────────────────────────────────────────────────────────

def generate_condition(cond_name: str, cond_cfg: dict, out_dir: str,
                        temperature: float = 0.85, top_p: float = 0.92):
    use_film         = cond_cfg["use_film"]
    use_scheduler    = cond_cfg["use_scheduler"]
    use_density_mask = cond_cfg["use_density_mask"]
    use_daw_postproc = cond_cfg["use_daw_postproc"]

    cond_out = os.path.join(out_dir, cond_name)
    os.makedirs(cond_out, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Condition: {cond_name}")
    print(f"  FiLM={use_film}  Scheduler={use_scheduler}  "
          f"DensityMask={use_density_mask}  DAWPostproc={use_daw_postproc}")
    print(f"{'='*60}")

    # Ensure project root is on sys.path so bare imports work (run from project root)
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Lazy-load generator
    if use_film:
        from inference.generate_cp_film import PulseCPFiLMGenerator
        gen = PulseCPFiLMGenerator(
            model_path=FILM_CKPT, vocab_path=VOCAB_PATH,
            use_scheduler=use_scheduler,
            use_density_mask=use_density_mask,
            use_daw_postproc=use_daw_postproc,
        )
    else:
        from inference.generate_cp import PulseCPGenerator
        gen = PulseCPGenerator(model_path=CP_CKPT, vocab_path=VOCAB_PATH)
        # Monkey-patch density mask and daw-postproc flags onto CP generator
        gen._use_density_mask = use_density_mask
        gen._use_daw_postproc = use_daw_postproc

    for blueprint in SONG_BLUEPRINTS:
        pid        = blueprint["id"]
        bpm        = blueprint["bpm"]
        out_path   = os.path.join(cond_out, f"{pid}.mid")

        if os.path.exists(out_path):
            print(f"  [SKIP] {pid}.mid already exists")
            continue

        print(f"\n  Generating {pid} ({bpm} BPM, {len(blueprint['sections'])} sections × 16 bars)")
        global_notes = defaultdict(list)
        offset_beats = 0.0

        for sec in blueprint["sections"]:
            prompt = make_prompt(sec, bpm, use_scheduler, use_film)
            e_for_section = sec["e_level"] if use_scheduler else 5

            max_tokens = sec["bars"] * 150

            if use_film:
                tokens = gen.generate(prompt, e_level=e_for_section,
                                      max_new_tokens=max_tokens,
                                      temperature=temperature, top_p=top_p)
                local_notes, _ = gen.tokens_to_note_dicts(
                    tokens, default_bpm=bpm, override_energy=e_for_section)
            else:
                tokens = gen.generate(prompt, max_new_tokens=max_tokens,
                                      temperature=temperature, top_p=top_p)
                local_notes, _ = gen.tokens_to_note_dicts(tokens, default_bpm=bpm)
                if not use_density_mask:
                    # Skip postprocess when density mask is off
                    pass  # CP generator always calls _postprocess_notes; re-parse raw
                    # (For strict w/o density mask under CP model, we'd need to bypass
                    #  _postprocess_notes — but this condition always uses FiLM model
                    #  per ablation design, so it won't reach here)

            max_seg_beats = sec["bars"] * 4.0
            for track, notes in local_notes.items():
                for n in notes:
                    if n["start_time"] >= max_seg_beats:
                        continue
                    if n["start_time"] + n["duration"] > max_seg_beats:
                        n["duration"] = max_seg_beats - n["start_time"]
                    n["start_time"] += offset_beats
                    global_notes[track].append(n)
            offset_beats += max_seg_beats

        total_bars = sum(s["bars"] for s in blueprint["sections"])
        if use_film:
            gen.dicts_to_midi(global_notes, bpm=bpm,
                              struct_bars=total_bars, output_path=out_path)
        else:
            gen.dicts_to_midi(global_notes, bpm=bpm,
                              struct_bars=total_bars, output_path=out_path)

        print(f"    -> Saved: {out_path}")

    print(f"\n  [DONE] {cond_name}")


# ── evaluation ────────────────────────────────────────────────────────────────

def run_eval(out_dir: str):
    eval_script = os.path.join("eval", "clean_ablation_eval.py")
    if not os.path.exists(eval_script):
        print(f"[ERROR] Eval script not found: {eval_script}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("  Running pipeline decomposition evaluation")
    print(f"{'='*60}")

    cmd = [
        sys.executable, eval_script,
        "--sweep_dir", out_dir,
        "--latex",
    ]
    print(f"  CMD: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[WARN] eval script exited with code {result.returncode}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    global FILM_CKPT, CP_CKPT, VOCAB_PATH  # declare before any reference

    parser = argparse.ArgumentParser()
    parser.add_argument("--step",        choices=["generate", "eval", "all"], default="all")
    parser.add_argument("--out_dir",     default="output/decomp_ablation")
    parser.add_argument("--conditions",  nargs="*", default=None,
                        help="Subset of conditions to generate (default: all 5)")
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--top_p",       type=float, default=0.92)
    parser.add_argument("--film_ckpt",   default=FILM_CKPT)
    parser.add_argument("--cp_ckpt",     default=CP_CKPT)
    parser.add_argument("--vocab_path",  default=VOCAB_PATH)
    args = parser.parse_args()

    FILM_CKPT  = args.film_ckpt
    CP_CKPT    = args.cp_ckpt
    VOCAB_PATH = args.vocab_path

    conditions_to_run = args.conditions or list(CONDITIONS.keys())
    invalid = [c for c in conditions_to_run if c not in CONDITIONS]
    if invalid:
        print(f"[ERROR] Unknown conditions: {invalid}. Valid: {list(CONDITIONS.keys())}")
        sys.exit(1)

    os.makedirs(args.out_dir, exist_ok=True)

    if args.step in ("generate", "all"):
        for cond_name in conditions_to_run:
            generate_condition(
                cond_name, CONDITIONS[cond_name], args.out_dir,
                temperature=args.temperature, top_p=args.top_p,
            )

    if args.step in ("eval", "all"):
        run_eval(args.out_dir)


if __name__ == "__main__":
    main()
