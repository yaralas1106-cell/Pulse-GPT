# PulseFormer Artifact Manifest

Date: 2026-05-04

This manifest inventories local artifacts that should be packaged, documented, or replaced with public equivalents before MTAP submission.

## Paper Source

- `docs/paper_draft.tex`: main Springer Nature manuscript source.
- `docs/references.bib`: BibTeX references.
- `docs/sn-jnl.cls`: Springer Nature journal class.
- `docs/sn-mathphys-num.bst`: numbered bibliography style.
- `docs/figures/`: manuscript figures.

## Public-Data Processing

- Primary GigaMIDI source: `Metacreation/GigaMIDI` on Hugging Face (`https://huggingface.co/datasets/Metacreation/GigaMIDI`), gated and subject to its stated license/access terms.
- Lakh MIDI Dataset source: `https://colinraffel.com/projects/lmd/`.
- `data_pipeline/process_gigamidi.py`
- `data_pipeline/filter_gigamidi.py`
- `data_pipeline/extract_lakh_edm.py`
- `data_pipeline/build_pulse_dataset.py`
- `data_pipeline/make_track_major.py`
- `data_pipeline/build_sota_datasets.py`

## Model and Tokenizer Code

- `core/model_cp.py`
- `core/model_cp_film.py`
- `core/tokenizer_cp.py`
- `core/dataset_cp.py`
- `core/dataset_cp_film.py`

## Generation Code

- `inference/generate_cp.py`
- `inference/generate_cp_film.py`
- `inference/generate_baseline_midi.py`
- `inference/generate_mos_samples.py`

## Evaluation Code

- `evaluation/evaluate_sota_baselines.py`
- `evaluation/extended_sota_eval.py`
- `evaluation/extended_sota_eval_n64.py`
- `evaluation/compute_bas.py`
- `evaluation/compute_irr.py`
- `evaluation/analyze_mos.py`
- `evaluation/compute_mos_bootstrap.py`
- `evaluation/audit_mos_sources.py`
- `eval/compute_jdm.py`

## Local Checkpoints

- `dataset/processed/m1_track_major_best.pt`
- `dataset/processed/m2_time_major_best.pt`
- `dataset/processed/m3_no_cond_best.pt`
- `dataset/processed/m4_simple_cond_best.pt`
- `dataset/processed/model_MMM.pt`
- `dataset/processed/model_CP.pt`
- `dataset/processed/model_REMI.pt`
- `checkpoints/pulsecp_v5_clean_best.pt`
- `checkpoints/pulsegpt_best.pt`
- `checkpoints/baseline_best.pt`

## Local Tokenizers and Datasets

- `dataset/processed/pulse_cp_vocab_5d_v6.json`
- `dataset/processed/pulse_cp_vocab_v6.json`
- `dataset/processed/pulse_dataset_v6.jsonl.gz`
- `dataset/processed/gigamidi_sequences.jsonl`
- `dataset/processed/lakh_sequences.jsonl`

## Current Generated Samples

- `outputs/pulsegpt/`: 10 PulseFormer MIDI samples available locally.
- `outputs/baseline/`: 10 MMM baseline MIDI samples available locally.
- `docs/mos_samples/`: 32 MOS MIDI stimuli: 8 prompts across 4 systems.
- `analysis/mos_results.csv`: current MOS rating table. This file must be reconciled with the manuscript MOS table before submission; see `docs/results/mos_consistency_audit.md`.

## Restricted or Non-Releasable Items

- Proprietary DAW project sequences described as 3% of the training corpus.
- Raw commercial/proprietary DAW project files, if any, should not be deposited.

## Required Before Submission

- Create a public repository or DOI-backed archive containing all releasable code, configs, prompts, generated samples, and public-data preprocessing instructions.
- Provide a public-only reproduction route that excludes proprietary DAW material.
- Reconcile the MOS raw data, table labels, pairwise tests, IRR values, and radar figure from one confirmed final rating file.
- Insert the final repository/DOI in `docs/paper_draft.tex`.
