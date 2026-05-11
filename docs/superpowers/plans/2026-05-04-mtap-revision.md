# MTAP Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `docs/paper_draft.tex` and `docs/paper_draft.pdf` to a submission-ready state for Multimedia Tools and Applications.

**Architecture:** Treat the revision as three linked workstreams: journal compliance, scientific evidence, and reproducible artifact packaging. Keep model/pipeline claims separated so reviewers can distinguish learned behavior from deterministic scheduling.

**Tech Stack:** LaTeX/Springer `sn-jnl`, Python evaluation scripts, MIDI/audio evaluation artifacts, BibTeX, MiKTeX or alternate TeX build.

---

### Task 1: Submission Compliance Pass

**Files:**
- Modify: `docs/paper_draft.tex`
- Modify: `docs/references.bib`
- Create: `docs/results/submission_checklist.md`

- [x] **Step 1: Fix abstract length**

Revise the abstract to 150--250 words while preserving all main claims and caveats.

- [x] **Step 2: Fix declarations heading**

Use `\section*{Statements and Declarations}`.

- [ ] **Step 3: Resolve ethics approval placeholder**

Replace `SHU-REC-2024-\textbf{XXXX}` with the actual approval number, or change the statement to an exemption/waiver statement if that is the approved status.

- [ ] **Step 4: Resolve code/data placeholder**

Add an anonymized repository, DOI, or archival link for checkpoint, tokenizer, section-detection pipeline, prompts, and evaluation scripts.

- [ ] **Step 5: Clean source-only mojibake and TODO comments**

Remove garbled comment lines near the declaration block and all `TODO`/`XXXX` placeholders.

Current status: decorative mojibake comment lines were removed from `docs/paper_draft.tex`, and a source scan reports 0 non-ASCII `%%` comment lines. The `SHU-REC-2024-XXXX` ethics placeholder and final artifact DOI/repository placeholder remain blocked because they require real external values.

- [ ] **Step 6: Rebuild PDF**

Run `pdflatex`, `bibtex`, `pdflatex`, `pdflatex` after the TeX environment is usable. Expected result: no fatal errors, no undefined citations/references.

### Task 2: Scientific Evidence Strengthening

**Files:**
- Modify: `eval/compute_jdm.py`
- Modify: `evaluation/evaluate_rigorous_paper_metrics.py`
- Create: `docs/results/full_jdm_n64.csv`
- Create: `docs/results/bootstrap_confidence_intervals.csv`

- [ ] **Step 1: Expand `J_DM` to all SOTA samples**

Run the within-bar drum-melody co-activation analysis on all `N=64` samples per trained model.

Current status: `eval/compute_jdm.py` now produces per-file and per-bar CSVs, and the available 10-vs-10 sample set has been recomputed as `docs/results/full_jdm_current_per_file.csv` and `docs/results/full_jdm_current_per_bar.csv`. Full `N=64` remains blocked until 64 generated MIDI files per trained model are generated or recovered.
The manuscript now uses the recomputed 10-vs-10 values and explicitly states that the per-file result is not statistically significant.

- [ ] **Step 2: Add bootstrap confidence intervals**

Compute 95% bootstrap confidence intervals for GPS, QN%, EB%, PCHE, ISR%, PR, and MOS dimensions.

Current status: `docs/results/bootstrap_confidence_intervals_current.csv` provides bootstrap 95% CIs for the current `J_DM` 10-vs-10 sample set, and `docs/results/mos_bootstrap_confidence_intervals_current.csv` provides rating-level MOS CIs from `analysis/mos_results.csv`. Full objective-metric CIs remain incomplete.

Additional blocker: `docs/results/mos_consistency_audit.md` reports that the manuscript MOS table does not match `analysis/mos_results.csv` in system labels or means. The MOS table, radar figure, pairwise tests, and IRR table must be regenerated from the final raw rating file.

- [ ] **Step 3: Add public-only sensitivity evidence**

Train or evaluate a public-only variant, or provide a source-ablation analysis showing whether the 3% proprietary DAW corpus materially changes the main conclusions.

- [ ] **Step 4: Update tables and text**

Revise SOTA, ablation, and MOS sections so every strong claim has either direct evidence or a clearly marked caveat.

### Task 3: Reproducibility Package

**Files:**
- Create: `docs/results/artifact_manifest.md`
- Create: `docs/results/reproduction_commands.md`
- Modify: `docs/paper_draft.tex`

- [x] **Step 1: Inventory releasable artifacts**

List tokenizer files, configs, trained checkpoints, evaluation scripts, prompts, generated MIDI, rendered audio, and public-data preprocessing scripts.

- [x] **Step 2: Separate restricted artifacts**

Document the 3% proprietary DAW data exclusion and provide public-only replacement instructions.

- [x] **Step 3: Add reproduction commands**

Write exact commands for dataset preprocessing, generation, objective evaluation, MOS statistics, and figure/table regeneration.

- [ ] **Step 4: Update Data Availability**

Replace generic release promises with precise public/private artifact statements.

Current status: external source links were made more precise in `docs/paper_draft.tex`: GigaMIDI is now named as the gated `Metacreation/GigaMIDI` Hugging Face dataset and Lakh MIDI keeps its public project URL. The final PulseFormer artifact repository/DOI is still missing.

### Task 4: Final PDF Quality Gate

**Files:**
- Modify: `docs/paper_draft.tex`
- Output: `docs/paper_draft.pdf`

- [ ] **Step 1: Compile cleanly**

Confirm no fatal LaTeX errors, undefined references, or missing citations.

- [ ] **Step 2: Inspect figures and tables**

Check all pages for unreadable figures, overfull tables, and cramped captions.

- [ ] **Step 3: Verify Springer source bundle**

Confirm the submission package includes `.tex`, `.bib`, `.bbl`, class/style files if needed, and all figure files in acceptable formats.

Current status: `docs/results/source_bundle_manifest.md` inventories all referenced source and figure files. The bundle is not submission-ready because the PDF/BBL are stale relative to the edited `.tex`, and the TeX environment is blocked.
Additional static check: `docs/results/static_latex_check.md` reports 0 missing references, 0 missing citation keys, 0 missing figure files, and balanced raw braces. This does not replace the final PDF build.
