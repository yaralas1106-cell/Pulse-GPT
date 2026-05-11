# MOS Consistency Audit

Date: 2026-05-04

## Source Data

- Rating CSV: `analysis/mos_results.csv`
- Rows: 800
- Participants: 25
- Prompts: 8
- Clips: 32
- Systems in the CSV: `Human`, `MMM`, `PulseFormer`, `REMI`
- Ratings per system: 200
- MOS dimensions in the CSV: `GT`, `SC`, `MV`, `Pref`

## Bootstrap Output

The current rating-level MOS bootstrap confidence intervals were written to:

- `docs/results/mos_bootstrap_confidence_intervals_current.csv`
- `docs/results/mos_source_inventory.csv`
- `docs/results/mos_source_inventory.md`

The script used to generate them is:

- `evaluation/compute_mos_bootstrap.py`
- `evaluation/audit_mos_sources.py`

Command:

```powershell
python evaluation\compute_mos_bootstrap.py --input analysis\mos_results.csv --output docs\results\mos_bootstrap_confidence_intervals_current.csv
```

## Current MOS Means From CSV

| System | GT mean | SC mean | MV mean | Pref mean |
| --- | ---: | ---: | ---: | ---: |
| Human | 3.865 | 4.310 | 4.095 | 3.930 |
| MMM | 3.080 | 2.170 | 2.470 | 2.385 |
| PulseFormer | 3.990 | 3.850 | 2.985 | 3.565 |
| REMI | 3.165 | 2.640 | 2.865 | 3.150 |

## Blocking Inconsistency

The manuscript MOS table currently reports the systems as `Human`, `PulseFormer`, `CP-Transformer`, and `MMM-Transformer`, while `analysis/mos_results.csv` contains `Human`, `PulseFormer`, `REMI`, and `MMM`.

The manuscript table values also do not match the CSV means exactly. Examples:

- Human SC is `4.24` in the manuscript table, but `4.310` in the CSV.
- PulseFormer SC is `3.76` in the manuscript table, but `3.850` in the CSV.
- PulseFormer MC is `3.52` in the manuscript table, while the CSV contains `Pref=3.565` and no `MC` column.
- The manuscript table includes `CP-Transformer`, but no `CP-Transformer` or `CP_Base` rows exist in the CSV.

## Required Fix Before Submission

The MOS section must be reconciled before the paper can be considered MTAP-ready:

1. Confirm whether the CSV system label `REMI` should replace `CP-Transformer` in the manuscript, or whether the correct CP-Transformer MOS CSV is missing.
2. Resolve the stimulus/rating mismatch: `docs/mos_samples` contains `CP_Base` stimuli but no `Human` stimuli, while `analysis/mos_results.csv` contains `Human` ratings but no `CP_Base` ratings.
3. Confirm whether `Pref` in the CSV is intended to be the manuscript's `MC`/Mix Clarity dimension, or whether the manuscript uses a different raw response file.
4. Regenerate the MOS table, radar figure, pairwise significance tests, and IRR table from the final raw rating file.
5. Archive the final raw rating CSV and exact analysis scripts in the artifact package.

Until these five items are resolved, the MOS evidence should be treated as internally inconsistent.
