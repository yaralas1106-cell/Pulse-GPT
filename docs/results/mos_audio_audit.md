# MOS Rendered-Audio Audit

Date: 2026-05-04

- Audio directory: `docs/mos_audio`
- MIDI directory: `docs/mos_samples`
- Rating CSV: `analysis/mos_results.csv`
- Minimum sanity-check size: 10000 bytes

## Label Alignment

| Label | Audio files | MIDI files | Rating rows |
| --- | ---: | ---: | ---: |
| CP_Base | 8 | 8 | 0 |
| Human | 0 | 0 | 200 |
| MMM | 8 | 8 | 200 |
| PulseFormer | 8 | 8 | 200 |
| REMI | 8 | 8 | 200 |

## Small Audio Files

- `REMI_P1.mp3`: 671 bytes.
- `REMI_P2.mp3`: 671 bytes.
- `REMI_P3.mp3`: 671 bytes.
- `REMI_P5.mp3`: 671 bytes.
- `REMI_P6.mp3`: 671 bytes.
- `REMI_P8.mp3`: 671 bytes.

## Interpretation

The rendered-audio assets support an audio-facing MOS protocol, but the label alignment remains unresolved: audio/MIDI assets contain `CP_Base` and `REMI`, while the current rating CSV contains `Human`, `MMM`, `PulseFormer`, and `REMI`. Several REMI MP3 files are extremely small and should be re-rendered or excluded after verification.
