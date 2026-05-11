# MOS Source Inventory

Date: 2026-05-04

- Stimuli directory: `docs/mos_samples`
- Rating CSV: `analysis/mos_results.csv`
- Manuscript source: `docs/paper_draft.tex`
- Stimulus MIDI files: 32
- Rating rows: 800

| Label | Stimulus MIDI files | Rating rows by model | Rating clip rows | In manuscript MOS table |
| --- | ---: | ---: | ---: | --- |
| CP-Transformer | 0 | 0 | 0 | True |
| CP_Base | 8 | 0 | 0 | False |
| Human | 0 | 200 | 200 | False |
| Human (Anchor) | 0 | 0 | 0 | True |
| MMM | 8 | 200 | 200 | False |
| MMM-Transformer | 0 | 0 | 0 | True |
| PulseFormer | 8 | 200 | 200 | False |
| PulseFormer (Ours) | 0 | 0 | 0 | True |
| REMI | 8 | 200 | 200 | False |

## Blocking Mismatches

- `CP_Base` has 8 stimulus MIDI files but no rating rows by model.
- `Human` has 200 rating rows but no matching stimulus MIDI files.
- Manuscript label `CP-Transformer` has no exact rating rows.

The final MOS section should use one confirmed label mapping and one final raw rating file.
