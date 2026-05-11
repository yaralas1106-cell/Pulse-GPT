# Springer Source Bundle Manifest

Date: 2026-05-04

This manifest checks the files needed to submit the current LaTeX manuscript source for MTAP/Springer review.

## Main Source Files

- `docs/paper_draft.tex` - present; last modified after the current PDF was built.
- `docs/references.bib` - present.
- `docs/paper_draft.bbl` - present, but stale relative to `paper_draft.tex` because PDF rebuild is currently blocked by MiKTeX setup.
- `docs/sn-jnl.cls` - present.
- `docs/sn-mathphys-num.bst` - present.

## Figure Files Referenced by `paper_draft.tex`

All referenced figure files are present:

- `docs/figures/architecture_new.png`
- `docs/figures/stitching.pdf`
- `docs/figures/sota_comparison.pdf`
- `docs/figures/failure_case.pdf`
- `docs/figures/attention_compare.pdf`
- `docs/figures/ablation_heatmap.pdf`
- `docs/figures/radar.pdf`

## Generated Files

- `docs/paper_draft.pdf` - present, but stale relative to the edited source.
- `docs/paper_draft.aux` - present, stale.
- `docs/paper_draft.log` - present, stale.
- `docs/paper_draft.out` - present, stale.

## Current Source Bundle Status

Not submission-ready yet.

Reasons:

- PDF and BBL were generated before the latest manuscript edits.
- Local MiKTeX currently exits before compilation due first-run setup/update registry access failure.
- Ethics approval placeholder remains in `docs/paper_draft.tex`.
- Data/code repository DOI or URL remains missing.
- Garbled source-only comments remain near the declarations block.

## Bundle Gate Before Submission

After TeX is usable, rebuild with:

```powershell
cd docs
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
bibtex paper_draft
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
pdflatex -interaction=nonstopmode -halt-on-error paper_draft.tex
```

Then confirm:

- No fatal LaTeX errors.
- No undefined citations or references.
- `paper_draft.pdf`, `paper_draft.bbl`, and `paper_draft.log` are newer than `paper_draft.tex`.
- All figures remain readable in the rebuilt PDF.
