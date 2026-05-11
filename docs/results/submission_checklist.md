# Journal Submission Checklist

Date: 2026-05-04

Current target: Journal on Audio, Speech, and Music Processing.

The earlier Springer-style checklist remains useful for source hygiene, but the current revision also tracks JASM-specific positioning in `docs/results/jasm_revision_audit.md`.

## Journal Compliance

- [x] Springer Nature `sn-jnl` class is used.
- [x] Published-style draft uses Springer Nature two-column layout (`iicol`) to match the JASM reference article.
- [x] Abstract is within 150--250 words: 223 words.
- [x] Keywords are within 4--6 items: 6 keywords.
- [x] `Declarations` section is present.
- [ ] Ethics approval number is final: currently blocked by `SHU-REC-2024-XXXX`.
- [ ] Code/data availability link is final: GigaMIDI/Lakh source links are now explicit, but the PulseFormer artifact repository or DOI is still required before submission.
- [ ] PDF compiles cleanly from source: blocked by local MiKTeX setup/update issue.
- [ ] All figures/tables visually inspected in the rebuilt PDF.

## Scientific Readiness

- [x] Paper distinguishes local FiLM controllability from deterministic scheduler enforcement.
- [x] Paper acknowledges GPS weakness and melodic-variety limitation.
- [x] Current `J_DM` analysis has reproducible CSV output for the local 10-vs-10 sample set.
- [x] Current `J_DM` bootstrap confidence intervals added for the local 10-vs-10 sample set.
- [x] Current output-level kick--bass/chord co-activation diagnostic added for the local 8-prompt MOS MIDI set: `docs/results/cross_track_coactivation_current_summary.csv`.
- [x] Current MOS bootstrap confidence intervals generated from `analysis/mos_results.csv`: `docs/results/mos_bootstrap_confidence_intervals_current.csv`.
- [x] MOS source inventory generated: `docs/results/mos_source_inventory.md` and `docs/results/mos_source_inventory.csv`.
- [ ] Full `N=64` `J_DM` and co-activation analysis completed: blocked because only 10 PulseFormer and 10 MMM generated MIDI files are present in `outputs/`, and the MOS set currently covers only 8 prompts.
- [ ] Bootstrap confidence intervals added for all objective metrics: current coverage is limited to `J_DM` and MOS.
- [ ] MOS section reconciled with raw rating data and stimulus files: `docs/results/mos_consistency_audit.md` and `docs/results/mos_source_inventory.md` flag blocking label/source mismatches.
- [ ] Public-only or source-ablation evidence added for the proprietary 3% corpus contribution.

## Source Package

- [x] Main source file exists: `docs/paper_draft.tex`.
- [x] Bibliography exists: `docs/references.bib`.
- [x] Springer class and bibliography style exist locally: `docs/sn-jnl.cls`, `docs/sn-mathphys-num.bst`.
- [x] Required figure files exist under `docs/figures/`.
- [x] Source bundle manifest created: `docs/results/source_bundle_manifest.md`.
- [x] Static LaTeX reference/citation/figure check passed: `docs/results/static_latex_check.md`.
- [x] Completion audit created: `docs/results/mtap_completion_audit.md`.
- [x] Source-only decorative mojibake comments removed from `docs/paper_draft.tex`; verified 0 non-ASCII `%%` comment lines remain.
- [ ] Submission ZIP/package assembled and verified.
