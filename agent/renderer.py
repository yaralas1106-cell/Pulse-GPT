"""
agent/renderer.py
=================
MIDI → audio conversion helpers.

Priority order:
  1. midi2audio (FluidSynth Python wrapper) → WAV → MP3 via pydub
  2. FluidSynth CLI directly             → WAV → MP3 via pydub
  3. Return MIDI path as fallback        (browser can't play, but download works)
"""

import subprocess
from pathlib import Path


def midi_to_audio(midi_path: Path, output_dir: Path, file_id: str) -> tuple[Path, str]:
    """
    Convert midi_path to an audio file in output_dir.
    Returns (audio_path, web_url_path).
    """
    mp3_path = output_dir / f"{file_id}.mp3"
    wav_path = output_dir / f"{file_id}.wav"

    # ── attempt 1: midi2audio ──────────────────────────────────────────────────
    try:
        from midi2audio import FluidSynth
        FluidSynth().midi_to_audio(str(midi_path), str(wav_path))
        _wav_to_mp3(wav_path, mp3_path)
        return mp3_path, f"/audio/{file_id}.mp3"
    except ImportError:
        pass
    except Exception:
        pass

    # ── attempt 2: fluidsynth CLI ──────────────────────────────────────────────
    sf2 = _find_soundfont()
    if sf2:
        try:
            subprocess.run(
                ["fluidsynth", "-ni", sf2, str(midi_path),
                 "-F", str(wav_path), "-r", "44100"],
                check=True, capture_output=True,
            )
            _wav_to_mp3(wav_path, mp3_path)
            return mp3_path, f"/audio/{file_id}.mp3"
        except Exception:
            pass

    # ── fallback: serve MIDI ───────────────────────────────────────────────────
    return midi_path, f"/audio/{file_id}.mid"


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    try:
        from pydub import AudioSegment
        AudioSegment.from_wav(str(wav_path)).export(str(mp3_path), format="mp3")
        wav_path.unlink(missing_ok=True)
    except Exception:
        mp3_path.unlink(missing_ok=True)
        raise


def _find_soundfont() -> str | None:
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
