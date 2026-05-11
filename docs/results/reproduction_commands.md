# Reproduction Commands

Date: 2026-05-04

These commands document the intended local reproduction flow. Paths are relative to the repository root.

## Paper Checks

```powershell
cd docs
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
bibtex paper_draft
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
```

Current blocker: local MiKTeX exits before compilation because its first-run setup/update state cannot write the required registry key.

## Current J_DM Recalculation

```powershell
python eval\compute_jdm.py `
  --pf_dir outputs\pulsegpt `
  --mmm_dir outputs\baseline `
  --out_prefix docs\results\full_jdm_current
```

Expected local outputs:

- `docs/results/full_jdm_current_per_file.csv`
- `docs/results/full_jdm_current_per_bar.csv`

Current local result:

- PulseFormer: 10 files, 142 bars, per-file mean `0.5593 +/- 0.1923`.
- MMM-Transformer: 10 files, 98 bars, per-file mean `0.4286 +/- 0.3185`.
- Per-bar Mann-Whitney U: `p=5.7648e-03`.
- Per-file Mann-Whitney U: `p=2.8479e-01`.

Important limitation: this is the available 10-vs-10 generated sample set, not the desired full `N=64` experiment.

## Existing N=64 Simulation Script

```powershell
python evaluation\extended_sota_eval_n64.py > docs\results\n64_result.txt
```

Important limitation: this script samples from preset metric distributions. It is useful for formatting and power-analysis scaffolding, but it is not a substitute for recomputing metrics from 64 generated MIDI files per system.

## Figure Regeneration

```powershell
python visualization\draw_quantitative_figures.py
python visualization\plot_attention_kick_bass.py
python visualization\plot_kl_vs_tau.py
```

## MOS Analysis

```powershell
python evaluation\analyze_mos.py analysis\mos_results.csv
python evaluation\compute_irr.py
python evaluation\compute_mos_bootstrap.py --input analysis\mos_results.csv --output docs\results\mos_bootstrap_confidence_intervals_current.csv
```

The MOS scripts should be rerun after the final response CSV or raw rating table is archived. Current blocker: `docs/results/mos_consistency_audit.md` shows that the manuscript MOS table does not match `analysis/mos_results.csv` in system labels or means, so the final MOS table, radar figure, pairwise tests, and IRR table must be regenerated from the confirmed final raw rating file.
